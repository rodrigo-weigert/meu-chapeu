import asyncio
import json
import random
import socket
import threading
import udp
import websockets

from voice_event import VoiceEvent, VoiceOpCode
from typing import Any, List, Callable, Awaitable
from config import Config
from logs import logger as base_logger
from concurrent.futures import ThreadPoolExecutor, Executor
from media_file import MediaFile
from dave.session import DaveSessionManager, DaveInvalidCommitException, TransitionType
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

logger = base_logger.bind(context="VoiceGatewayClient")


class VoiceClient:
    _guild_id: str
    _channel_id: str
    _url: str
    _session_id: str
    _token: str
    _on_close: Callable[[], Awaitable[Any]]
    _config: Config
    _ssrc: int
    _audio_seq: int
    _last_seq: int
    _rtp_nonce: int
    _closed: bool
    _executor: Executor
    _session_ready: asyncio.Event
    _dave_session_ready: asyncio.Event
    _idle_timer: asyncio.Task | None
    _player: asyncio.Task
    _media_queue: asyncio.Queue
    _stop_event: threading.Event | None
    _dave_session_manager: DaveSessionManager
    _external_sender_ready: asyncio.Event
    _identified: bool
    _ws: websockets.ClientConnection
    _sock: socket.socket
    _transport_encryption_mode: str
    _transport_encryption_key: List[int]
    _recv_loop: asyncio.Task

    def __init__(
        self,
        guild_id: str,
        channel_id: str,
        url: str,
        session_id: str,
        token: str,
        on_close: Callable[[], Awaitable[Any]],
        config: Config,
    ) -> None:
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._url = f"wss://{url}?v=8"
        self._session_id = session_id
        self._token = token
        self._on_close = on_close
        self._config = config

        self._ssrc = 0
        self._audio_seq = random.getrandbits(32)
        self._last_seq = -1
        self._rtp_nonce = random.getrandbits(32)
        self._closed = False
        self._executor = ThreadPoolExecutor()
        self._session_ready = asyncio.Event()
        self._dave_session_ready = asyncio.Event()
        self._idle_timer = None
        self._player = asyncio.create_task(self._play_loop())
        self._media_queue = asyncio.Queue()
        self._stop_event = None
        self._dave_session_manager = DaveSessionManager(self._config.application_id)
        self._external_sender_ready = asyncio.Event()
        self._identified = False

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def closed(self) -> bool:
        return self._closed

    async def start(self) -> None:
        self._ws = await websockets.connect(self._url)
        try:
            self._recv_loop = asyncio.create_task(self._receive_loop())
            await self._recv_loop
        except asyncio.exceptions.CancelledError:
            logger.info("Receive loop task cancelled")
        finally:
            await self._close()

    async def enqueue_media(self, media: MediaFile) -> None:
        asyncio.get_running_loop().run_in_executor(self._executor, media.download)
        await self._media_queue.put(media)

    def skip_current_media(self) -> bool:
        if self._stop_event is not None:
            self._stop_event.set()
            return True
        return False

    async def _send(self, op: VoiceOpCode, data: Any) -> None:
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))
        # TODO have logger.log("OUT",...) only here and remove all others?

    async def _send_binary(self, op: VoiceOpCode, data: bytes) -> None:
        await self._ws.send(op.value.to_bytes(length=1) + data)

    async def _send_heartbeat(self, nonce: int) -> None:
        await self._send(VoiceOpCode.HEARTBEAT, {"seq_ack": self._last_seq, "t": nonce})
        logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}, nonce = {nonce}")

    async def _regular_heartbeats(self, heartbeat_interval: float) -> None:
        heartbeat_nonce = random.randint(1000000000000, 1999999999999)
        while True:
            try:
                await self._send_heartbeat(heartbeat_nonce)
            except websockets.exceptions.ConnectionClosed:
                return
            await asyncio.sleep(heartbeat_interval)
            heartbeat_nonce += 1

    async def _identify(self) -> None:
        data = {
            "token": self._token,
            "server_id": self._guild_id,
            "user_id": self._config.application_id,
            "session_id": self._session_id,
            "max_dave_protocol_version": 1,
        }
        logger.log("OUT", f"IDENTIFY guild_id = {self._guild_id}")
        await self._send(VoiceOpCode.IDENTIFY, data)

    async def _send_key_package(self) -> None:
        key_package = self._dave_session_manager.get_key_package_message()
        await self._send_binary(VoiceOpCode.DAVE_MLS_KEY_PACKAGE, key_package)
        logger.log("OUT", "DAVE MLS KEY PACKAGE")

    async def _handle_hello(self, event: VoiceEvent) -> None:
        logger.log("IN", f"HELLO {event}")

        if self._identified:
            return

        heartbeat_interval = event["heartbeat_interval"] / 1000
        await self._identify()
        asyncio.create_task(self._regular_heartbeats(heartbeat_interval))

    def _prepare_socket(self, ip: str, port: int) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("0.0.0.0", 2917))  # TODO should use a port range to support multiple simultaneous voice connections
        self._sock.connect((ip, port))

    async def _handle_ready(self, event: VoiceEvent) -> None:
        logger.log("IN", f"VOICE READY {event}")
        self._identified = True
        ip, port, ssrc, modes = event["ip"], event["port"], event["ssrc"], event["modes"]
        self._transport_encryption_mode = "aead_aes256_gcm_rtpsize" if "aead_aes256_gcm_rtpsize" in modes else "aead_xchacha20_poly1305_rtpsize"
        self._ssrc = ssrc
        self._prepare_socket(ip, port)
        my_ip, my_port = udp.do_ip_discovery(self._sock, ssrc)
        logger.log("OUT", f"SELECT PROTOCOL encryption mode = {self._transport_encryption_mode}")
        await self._send(VoiceOpCode.SELECT_PROTOCOL,
                         {"protocol": "udp",
                          "data": {"address": my_ip,
                                   "port": my_port,
                                   "mode": self._transport_encryption_mode}})

    async def _ensure_ready(self) -> None:
        if self._session_ready.is_set() and self._dave_session_ready.is_set():
            return
        logger.info("Waiting for session to be ready...")
        await self._session_ready.wait()
        await self._dave_session_ready.wait()

    async def _play_song(self, media_file: MediaFile) -> None:
        await self._ensure_ready()

        logger.info(f"Now playing {media_file}")
        self._stop_event = threading.Event()
        sent_packets = await asyncio.get_running_loop().run_in_executor(
            self._executor,
            udp.stream_audio,
            self._sock,
            media_file,
            self._ssrc,
            self._audio_seq,
            self._transport_encryption_key,
            self._rtp_nonce,
            self._transport_encryption_mode,
            self._stop_event,
            self._dave_session_manager,
        )
        self._audio_seq += sent_packets
        self._rtp_nonce += sent_packets
        self._stop_event = None

    async def _play_loop(self) -> None:
        try:
            while True:
                logger.info("Waiting for next song in queue...")

                if self._media_queue.qsize() == 0:
                    self._idle_timer = asyncio.create_task(self._disconnect_after_delay())

                next_media = await self._media_queue.get()

                if self._idle_timer is not None:
                    self._idle_timer.cancel()
                    self._idle_timer = None

                logger.info(f"Waiting for download of {next_media} to complete...")
                ready = await next_media.downloaded
                if ready:
                    await self._play_song(next_media)
                else:
                    logger.warning(f"Download of {next_media} did not succeed, skipping")
        except asyncio.CancelledError:
            logger.info("Play loop cancelled")

    async def _handle_session_description(self, event: VoiceEvent) -> None:
        logger.log("IN", f"SESSION DESCRIPTION {event}")

        self._transport_encryption_key = event["secret_key"]

        speaking_payload = {"ssrc": self._ssrc, "speaking": (1 << 0), "delay": 0}
        await self._send(VoiceOpCode.SPEAKING, speaking_payload)
        logger.log("OUT", f"SPEAKING {speaking_payload}")

        if event["dave_protocol_version"] > 0:
            await self._send_key_package()
        else:
            self._dave_session_ready.set()

        self._session_ready.set()

    def _handle_dave_mls_external_sender(self, event: VoiceEvent) -> None:
        logger.log("IN", "DAVE MLS EXTERNAL SENDER")

        identity = event["external_sender"]["credential"]["identity"]
        signature_key = event["external_sender"]["signature_key"]

        self._dave_session_manager.set_external_sender(identity, signature_key)
        self._external_sender_ready.set()

    async def _handle_dave_mls_welcome(self, event: VoiceEvent) -> None:
        transition_id = event["transition_id"]
        logger.log("IN", f"DAVE MLS WELCOME (transition_id = {transition_id})")

        await asyncio.wait_for(self._external_sender_ready.wait(), timeout=10.0)

        self._dave_session_manager.stage_transition_from_welcome(transition_id, event["welcome_message"])

        if transition_id == 0:
            self._dave_session_manager.execute_transition(0)
            logger.info("DAVE transition successfully executed (initial group creation - immediate transition from welcome)")
            self._dave_session_ready.set()
        else:
            await self._send(VoiceOpCode.DAVE_TRANSITION_READY, {"transition_id": transition_id})
            logger.log("OUT", f"DAVE TRANSITION READY (transition_id = {transition_id})")

    def _handle_dave_execute_transition(self, event: VoiceEvent) -> None:
        transition_id = event["transition_id"]
        logger.log("IN", f"DAVE EXECUTE TRANSITION (transition_id = {transition_id})")

        transition_type = self._dave_session_manager.execute_transition(transition_id)
        if transition_type is not None:
            logger.info(f"DAVE transition {transition_id} successfully executed (type = {transition_type})")
        else:
            logger.info(f"DAVE transition {transition_id} ignored")
            return

        if transition_type == TransitionType.DOWNGRADE:
            self._external_sender_ready.clear()
        else:
            self._dave_session_ready.set()

    async def _handle_dave_mls_proposals(self, event: VoiceEvent) -> None:
        operation_type = event["operation_type"]
        logger.log("IN", f"DAVE MLS PROPOSALS (operation_type = {operation_type})")

        match operation_type:
            case 0:  # Append
                await asyncio.wait_for(self._external_sender_ready.wait(), timeout=10.0)

                commit_welcome_message = self._dave_session_manager.append_proposals(event["proposal_messages"])

                if commit_welcome_message is not None:
                    await self._send_binary(VoiceOpCode.DAVE_MLS_COMMIT_WELCOME, commit_welcome_message)
                    logger.log("OUT", "DAVE MLS COMMIT WELCOME")
                else:
                    logger.info("Proposal processing skipped")
            case 1:  # Revoke
                raise NotImplementedError("No support for revoking proposals")
            case _:
                raise ValueError(f"Unknown DAVE MLS PROPOSALS operation type: {operation_type}")

    async def _invalid_commit_recovery(self, transition_id: int) -> None:
        logger.warning("Received invalid commit, starting recovery flow")

        self._dave_session_manager.reset_session()

        await self._send(VoiceOpCode.DAVE_MLS_INVALID_COMMIT_WELCOME, {"transition_id": transition_id})
        logger.log("OUT", f"DAVE MLS INVALID COMMIT WELCOME (transition_id = {transition_id})")

        await self._send_key_package()

    async def _handle_dave_mls_announce_commit_transition(self, event: VoiceEvent) -> None:
        transition_id = event["transition_id"]
        logger.log("IN", f"DAVE MLS ANNOUNCE COMMIT TRANSITION (transition_id = {transition_id})")

        try:
            self._dave_session_manager.stage_transition_from_commit(transition_id, event["commit_message"])
        except DaveInvalidCommitException:
            await self._invalid_commit_recovery(transition_id)
            return

        if transition_id == 0:
            self._dave_session_manager.execute_transition(0)
            logger.info("DAVE transition successfully executed (initial group creation - immediate transition from own commit)")
            self._dave_session_ready.set()
        else:
            await self._send(VoiceOpCode.DAVE_TRANSITION_READY, {"transition_id": transition_id})
            logger.log("OUT", f"DAVE TRANSITION READY (transition_id = {transition_id})")

    def _handle_dave_prepare_transition(self, event: VoiceEvent) -> None:
        transition_id = event["transition_id"]
        protocol_version = event["protocol_version"]
        logger.log("IN", f"DAVE PREPARE TRANSITION (transition_id = {transition_id}, protocol_version = {protocol_version})")

        if protocol_version == 0:
            self._dave_session_manager.stage_downgrade_transition(transition_id)
        elif protocol_version == 1:
            if transition_id == 0:
                logger.info("DAVE sole member reset")
            else:
                raise NotImplementedError("No support for preparing DAVE transitions to protocol version 1 except for sole member resets")
        else:
            raise NotImplementedError("No support for DAVE transitions to versions higher than 1")

    async def _handle_dave_prepare_epoch(self, event: VoiceEvent) -> None:
        dave_version = event["protocol_version"]
        epoch = event["epoch"]
        logger.log("IN", f"DAVE PREPARE EPOCH (dave_version = {dave_version}, epoch = {epoch})")

        if dave_version != 1:
            raise NotImplementedError(f"No support for transition to DAVE protocol version {dave_version}")

        if epoch == 1:  # Either upgrade from transport-only, or sole member reset
            self._dave_session_manager.reset_session()
            await self._send_key_package()

    async def _reconnect(self) -> None:
        logger.info("Reconnecting...")
        try:
            self._ws = await websockets.connect(self._url)
            resume = {
                "server_id": self._guild_id,
                "session_id": self._session_id,
                "token": self._token,
                "seq_ack": self._last_seq
            }
            await self._send(VoiceOpCode.RESUME, resume)
            logger.log("OUT", f"RESUME (server_id = {self._guild_id})")
        except Exception as e:
            logger.warning(f"Failed to reconnect: {e}")

    async def _handle_disconnection(self, exception: ConnectionClosed) -> bool:
        if _kicked_or_call_terminated(exception):
            logger.info(f"Kicked from channel or call terminated: {exception}")
            return False

        if isinstance(exception, ConnectionClosedOK):
            logger.info(f"Connection closed (OK): {exception}")
        else:
            logger.warning(f"Connection closed (error): {exception}")

        if _should_reconnect(exception):
            await self._reconnect()
            return True
        return False

    async def _receive_loop(self) -> None:
        while True:
            try:
                event = VoiceEvent(await self._ws.recv())
            except websockets.exceptions.ConnectionClosed as e:
                if await self._handle_disconnection(e):
                    continue
                else:
                    logger.info("Reconnection is not allowed. Closing client.")
                    return

            if event.seq_num:
                self._last_seq = event.seq_num

            match event.opcode:
                case VoiceOpCode.HELLO:
                    asyncio.create_task(self._handle_hello(event))
                case VoiceOpCode.HEARTBEAT_ACK:
                    logger.log("IN", "VOICE HEARTBEAT ACK")
                case VoiceOpCode.READY:
                    asyncio.create_task(self._handle_ready(event))
                case VoiceOpCode.SESSION_DESCRIPTION:
                    asyncio.create_task(self._handle_session_description(event))
                case VoiceOpCode.DAVE_MLS_EXTERNAL_SENDER:
                    self._handle_dave_mls_external_sender(event)
                case VoiceOpCode.DAVE_MLS_WELCOME:
                    asyncio.create_task(self._handle_dave_mls_welcome(event))
                case VoiceOpCode.DAVE_EXECUTE_TRANSITION:
                    self._handle_dave_execute_transition(event)
                case VoiceOpCode.DAVE_MLS_PROPOSALS:
                    asyncio.create_task(self._handle_dave_mls_proposals(event))
                case VoiceOpCode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION:
                    await self._handle_dave_mls_announce_commit_transition(event)
                case VoiceOpCode.DAVE_PREPARE_TRANSITION:
                    self._handle_dave_prepare_transition(event)
                case VoiceOpCode.DAVE_PREPARE_EPOCH:
                    await self._handle_dave_prepare_epoch(event)
                case VoiceOpCode.RESUMED:
                    logger.info("Connection resumed successfully")
                case _:
                    logger.log("IN", f"UNHANDLED VOICE EVENT {event}")

    async def _close(self) -> None:
        if self._closed:
            return
        self._recv_loop.cancel(msg="Close method was called")
        self._player.cancel(msg="Close method was called")
        await self._ws.close()
        if self._sock is not None:
            self._sock.close()
        await self._on_close()
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        self._closed = True

    async def _disconnect_after_delay(self) -> None:
        logger.info("Idle timer started")
        try:
            await asyncio.sleep(self._config.idle_timeout)
            if not self._closed:
                logger.info(f"Bot was idle for {self._config.idle_timeout} seconds, disconnecting")
                await self._close()
        except asyncio.CancelledError:
            logger.info("Idle timer cancelled")


_ALLOWED_RECONNECT_CLOSE_CODES = {1001, 1006, 4015}


def _should_reconnect(exception: ConnectionClosed) -> bool:
    return exception.rcvd is None or exception.rcvd.code in _ALLOWED_RECONNECT_CLOSE_CODES


def _kicked_or_call_terminated(exception: ConnectionClosed) -> bool:
    return exception.rcvd is not None and exception.rcvd.code in {4014, 4022}

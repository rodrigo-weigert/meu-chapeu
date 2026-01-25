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
from dave.session import DaveSessionManager

logger = base_logger.bind(context="VoiceGatewayClient")


class VoiceClient:
    _guild_id: str
    _channel_id: str
    _url: str
    _session_id: str
    _token: str
    _config: Config
    _ssrc: int
    _audio_seq: int
    _closed: bool
    _last_seq: int
    _ws: websockets.ClientConnection
    _sock: socket.socket
    _encryption_key: List[int]
    _executor: Executor
    _nonce: int
    _encryption_mode: str
    _session_ready: asyncio.Event
    _dave_session_ready: asyncio.Event
    _idle_timer: asyncio.Task | None
    _receive_loop: asyncio.Task
    _player: asyncio.Task
    _on_close: Callable[[], Awaitable[Any]]
    _media_queue: asyncio.Queue
    _stop_event: threading.Event | None
    _external_sender_event: asyncio.Event
    _dave_session_manager: DaveSessionManager

    def __init__(self, guild_id: str, channel_id: str, url: str, session_id: str, token: str, on_close: Callable[[], Awaitable[Any]], config: Config):
        self._url = f"wss://{url}?v=8"
        self._session_id = session_id
        self._token = token
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._config = config
        self._last_seq = -1
        self._encryption_key = []
        self._ssrc = 0
        self._audio_seq = random.getrandbits(32)
        self._rtp_nonce = random.getrandbits(32)
        self._session_ready = asyncio.Event()
        self._dave_session_ready = asyncio.Event()
        self._executor = ThreadPoolExecutor()
        self._closed = False
        self._on_close = on_close
        self._media_queue = asyncio.Queue()
        self._player = asyncio.create_task(self.play_loop())
        self._idle_timer = None
        self._stop_event = None
        self._dave_session_manager = DaveSessionManager(self._config.application_id)
        self._external_sender_ready = asyncio.Event()

    @property
    def channel_id(self):
        return self._channel_id

    @property
    def closed(self):
        return self._closed

    async def send(self, op: VoiceOpCode, data: Any):
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_binary(self, op: VoiceOpCode, data: bytes):
        await self._ws.send(op.value.to_bytes(1) + data)

    async def send_heartbeat(self, nonce: int):
        await self.send(VoiceOpCode.HEARTBEAT, {"seq_ack": self._last_seq,
                                                "t": nonce})
        logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}, nonce = {nonce}")

    async def regular_heartbeats(self, heartbeat_interval: float):
        heartbeat_nonce = random.randint(1000000000000, 1999999999999)
        while True:
            try:
                await self.send_heartbeat(heartbeat_nonce)
            except websockets.exceptions.ConnectionClosed:
                return
            await asyncio.sleep(heartbeat_interval)
            heartbeat_nonce += 1

    async def identify(self):
        data = {"token": self._token,
                "server_id": self._guild_id,
                "user_id": self._config.application_id,
                "session_id": self._session_id,
                "max_dave_protocol_version": 1}
        logger.log("OUT", f"IDENTIFY guild_id = {self._guild_id}")
        await self.send(VoiceOpCode.IDENTIFY, data)

    async def handle_hello(self, event: VoiceEvent):
        logger.log("IN", f"HELLO {event}")
        heartbeat_interval = event.get("heartbeat_interval") / 1000
        await self.identify()
        asyncio.create_task(self.regular_heartbeats(heartbeat_interval))

    def _prepare_socket(self, ip: str, port: int) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("0.0.0.0", 2917))  # TODO should use a port range to support multiple simultaneous voice connections
        self._sock.connect((ip, port))

    async def handle_ready(self, event: VoiceEvent):
        logger.log("IN", f"VOICE READY {event}")
        ip, port, ssrc, modes = event.get("ip"), event.get("port"), event.get("ssrc"), event.get("modes")
        self.encryption_mode = "aead_aes256_gcm_rtpsize" if "aead_aes256_gcm_rtpsize" in modes else "aead_xchacha20_poly1305_rtpsize"
        self._ssrc = ssrc
        self._prepare_socket(ip, port)
        my_ip, my_port = udp.do_ip_discovery(self._sock, ssrc)
        logger.log("OUT", f"SELECT PROTOCOL encryption mode = {self.encryption_mode}")
        await self.send(VoiceOpCode.SELECT_PROTOCOL,
                        {"protocol": "udp",
                         "data": {"address": my_ip,
                                  "port": my_port,
                                  "mode": self.encryption_mode}})

    async def ensure_ready(self) -> None:
        if self._session_ready.is_set() and self._dave_session_ready.is_set():
            return
        logger.info("Waiting for session to be ready...")
        await self._session_ready.wait()
        await self._dave_session_ready.wait()

    async def play_song(self, media_file: MediaFile) -> None:
        await self.ensure_ready()

        logger.info(f"Now playing {media_file}")
        self._stop_event = threading.Event()
        packets = media_file.packets()
        sent_packets = await asyncio.get_running_loop().run_in_executor(self._executor, udp.stream_audio, self._sock, packets, self._ssrc, self._audio_seq, self._encryption_key, self._rtp_nonce, self.encryption_mode, self._stop_event, self._dave_session_manager)
        self._audio_seq += sent_packets
        self._rtp_nonce += sent_packets
        self._stop_event = None

    async def play_loop(self):
        try:
            while True:
                logger.info("Waiting for next song in queue...")

                if self._media_queue.qsize() == 0:
                    self._idle_timer = asyncio.create_task(self.disconnect_after_delay())

                next_media = await self._media_queue.get()

                if self._idle_timer is not None:
                    self._idle_timer.cancel()

                logger.info(f"Waiting for download of {next_media} to complete...")
                ready = await next_media.downloaded
                if ready:
                    await self.play_song(next_media)
                else:
                    logger.warning(f"Download of {next_media} did not succeed, skipping")
        except asyncio.CancelledError:
            logger.info("Play loop cancelled")

    async def enqueue_media(self, media: MediaFile):
        asyncio.get_running_loop().run_in_executor(self._executor, media.download)
        await self._media_queue.put(media)

    def skip_current_media(self) -> bool:
        if self._stop_event is not None:
            self._stop_event.set()
            return True
        return False

    async def handle_session_description(self, event: VoiceEvent):
        logger.log("IN", f"SESSION DESCRIPTION {event}")

        self._encryption_key = event.get("secret_key")

        speaking_payload = {"ssrc": self._ssrc, "speaking": (1 << 0), "delay": 0}
        await self.send(VoiceOpCode.SPEAKING, speaking_payload)
        logger.log("OUT", f"SPEAKING {speaking_payload}")

        if event.get("dave_protocol_version") > 0:
            key_package = self._dave_session_manager.get_key_package_message()
            await self.send_binary(VoiceOpCode.DAVE_MLS_KEY_PACKAGE, key_package)
            logger.log("OUT", "DAVE MLS KEY PACKAGE")
        else:
            self._dave_session_ready.set()

        self._session_ready.set()

    def handle_dave_mls_external_sender(self, event: VoiceEvent):
        logger.log("IN", "DAVE MLS EXTERNAL SENDER")

        identity = event.get("external_sender").credential.identity
        signature_key = event.get("external_sender").signature_key

        self._dave_session_manager.set_external_sender(identity, signature_key)
        self._external_sender_ready.set()

    async def handle_dave_mls_welcome(self, event: VoiceEvent):
        transition_id = event.get("transition_id")
        logger.log("IN", f"DAVE MLS WELCOME (transition_id = {transition_id})")

        await asyncio.wait_for(self._external_sender_ready.wait(), timeout=10.0)

        self._dave_session_manager.stage_transition_from_welcome(transition_id, event.get("welcome_message"))

        if transition_id == 0:  # Initial group creation - may need the same logic for opcode 29 (DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION)
            self._dave_session_manager.execute_transition(0)
            logger.info("DAVE transition successfully executed (initial group creation - skipped waiting for DAVE_EXECUTE_TRANSITION)")
            self._dave_session_ready.set()
        else:
            await self.send(VoiceOpCode.DAVE_TRANSITION_READY, {"transition_id": transition_id})
            logger.log("OUT", f"DAVE TRANSITION READY (transition_id = {transition_id})")

    def handle_dave_execute_transition(self, event: VoiceEvent):
        transition_id = event.get("transition_id")
        logger.log("IN", f"DAVE EXECUTE TRANSITION (transition_id = {transition_id})")

        self._dave_session_manager.execute_transition(transition_id)
        logger.info(f"DAVE transition successfully executed (transition_id = {transition_id})")

        self._dave_session_ready.set()

    async def handle_dave_mls_proposals(self, event: VoiceEvent):
        operation_type = event.get("operation_type")
        logger.log("IN", f"DAVE MLS PROPOSALS (operation_type = {operation_type})")

        # Code below currently would only work when at initial group creation phase
        # However, it is not necessary. We can choose to opt out of sending the commit
        # that establishes the group.

        # if operation_type == 0:  # Append proposals
        #     await asyncio.wait_for(self._external_sender_ready.wait(), timeout=10.0)
        #
        #     commit_welcome_message = self.dave_session_manager.process_proposals(event.get("proposal_messages"))

        #     await self.send_binary(VoiceOpCode.DAVE_MLS_COMMIT_WELCOME, commit_welcome_message)
        #     logger.log("OUT", "DAVE MLS COMMIT WELCOME")

    async def receive_loop(self):
        while True:
            try:
                event = VoiceEvent(await self._ws.recv())
            except websockets.exceptions.ConnectionClosedOK as e:
                logger.info(f"Connection normal closure (code {e.code}), stopping client")
                return
            except websockets.exceptions.ConnectionClosedError as e:
                if e.code == 4014:
                    logger.info("Connection closed due to disconnect (kicked from channel?), stopping client")
                else:
                    logger.warning(f"Connection closed with error (code {e.code}), stopping client")
                return

            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case VoiceOpCode.HELLO:
                    asyncio.create_task(self.handle_hello(event))
                case VoiceOpCode.HEARTBEAT_ACK:
                    logger.log("IN", "VOICE HEARTBEAT ACK")
                case VoiceOpCode.READY:
                    asyncio.create_task(self.handle_ready(event))
                case VoiceOpCode.SESSION_DESCRIPTION:
                    asyncio.create_task(self.handle_session_description(event))
                case VoiceOpCode.DAVE_MLS_EXTERNAL_SENDER:
                    self.handle_dave_mls_external_sender(event)
                case VoiceOpCode.DAVE_MLS_WELCOME:
                    asyncio.create_task(self.handle_dave_mls_welcome(event))
                case VoiceOpCode.DAVE_EXECUTE_TRANSITION:
                    self.handle_dave_execute_transition(event)
                case VoiceOpCode.DAVE_MLS_PROPOSALS:
                    asyncio.create_task(self.handle_dave_mls_proposals(event))
                case _:
                    logger.log("IN", f"UNHANDLED VOICE EVENT {event}")

    async def close(self) -> None:
        if self._closed:
            return
        self._receive_loop.cancel(msg="Close method was called")
        self._player.cancel(msg="Close method was called")
        await self._ws.close()
        if self._sock is not None:
            self._sock.close()
        await self._on_close()
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        self._closed = True

    async def disconnect_after_delay(self) -> None:
        logger.info("Idle timer started")
        try:
            await asyncio.sleep(self._config.idle_timeout)
            if not self._closed:
                logger.info(f"Bot was idle for {self._config.idle_timeout} seconds, disconnecting")
                await self.close()
        except asyncio.CancelledError:
            logger.info("Idle timer cancelled")

    async def start(self):
        self._ws = await websockets.connect(self._url)
        try:
            self._receive_loop = asyncio.create_task(self.receive_loop())
            await self._receive_loop
        except asyncio.exceptions.CancelledError:
            logger.info("Receive loop task cancelled")
        finally:
            await self.close()

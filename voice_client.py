import asyncio
import json
import opus
import random
import socket
import udp
import websockets

from voice_event import VoiceEvent, VoiceOpCode
from typing import Any, List
from config import Config
from logs import logger as base_logger

logger = base_logger.bind(context="VoiceGatewayClient")


class VoiceClient:
    guild_id: str
    channel_id: str
    url: str
    session_id: str
    token: str
    config: Config
    ssrc: int
    audio_seq: int
    _last_seq: int
    _ws: websockets.ClientConnection
    _sock: socket.socket
    _encryption_key: List[int]
    nonce: int
    encryption_mode: str
    ready: asyncio.Event

    def __init__(self, guild_id: str, channel_id: str, url: str, session_id: str, token: str, config: Config):
        self.url = f"wss://{url}?v=8"
        self.session_id = session_id
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.config = config
        self._last_seq = -1
        self._encryption_key = []
        self.ssrc = 0
        self.audio_seq = random.getrandbits(32)
        self.nonce = random.getrandbits(32)
        self.ready = asyncio.Event()

    async def send(self, op: VoiceOpCode, data: Any):
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_heartbeat(self, nonce: int):
        logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}, nonce = {nonce}")
        await self.send(VoiceOpCode.HEARTBEAT, {"seq_ack": self._last_seq,
                                                "t": nonce})

    async def regular_heartbeats(self, heartbeat_interval: float):
        heartbeat_nonce = random.randint(1000000000000, 1999999999999)
        while True:
            await self.send_heartbeat(heartbeat_nonce)
            await asyncio.sleep(heartbeat_interval)
            heartbeat_nonce += 1

    async def identify(self):
        data = {"token": self.token,
                "server_id": self.guild_id,
                "user_id": self.config.application_id,
                "session_id": self.session_id,
                "max_dave_protocol_version": 0}
        logger.log("OUT", f"IDENTIFY guild_id = {self.guild_id}")
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
        self.ssrc = ssrc
        self._prepare_socket(ip, port)
        my_ip, my_port = udp.do_ip_discovery(self._sock, ssrc)
        logger.log("OUT", f"SELECT PROTOCOL encryption mode = {self.encryption_mode}")
        await self.send(VoiceOpCode.SELECT_PROTOCOL,
                        {"protocol": "udp",
                         "data": {"address": my_ip,
                                  "port": my_port,
                                  "mode": self.encryption_mode}})

    async def play_song(self, media_file_name: str) -> None:
        await self.ready.wait()
        packets = opus.encode(media_file_name)
        await udp.stream_audio(self._sock, packets, self.ssrc, self.audio_seq, self._encryption_key, self.nonce, self.encryption_mode)
        self.audio_seq += len(packets)
        self.nonce += len(packets)

    async def handle_session_description(self, event: VoiceEvent):
        logger.log("IN", f"SESSION DESCRIPTION {event}")
        self._encryption_key = event.get("secret_key")
        logger.info(f"Encryption key: {self._encryption_key}")
        speaking_payload = {"ssrc": self.ssrc, "speaking": (1 << 0), "delay": 0}
        logger.log("OUT", f"SPEAKING {speaking_payload}")
        await self.send(VoiceOpCode.SPEAKING, speaking_payload)
        self.ready.set()

    async def receive_loop(self):
        while True:
            event = VoiceEvent(await self._ws.recv())
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
                case _:
                    logger.log("IN", f"VOICE UNKNOWN {event}")

    async def start(self):
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except asyncio.exceptions.CancelledError:
            pass
        finally:
            await self._ws.close()
            if self._sock is not None:
                self._sock.close()

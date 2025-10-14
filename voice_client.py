import asyncio
import json
import random
import socket
import struct
import websockets

from voice_event import VoiceEvent, VoiceOpCode
from typing import Any
from config import Config


class VoiceClient:
    guild_id: str
    url: str
    session_id: str
    token: str
    config: Config
    _last_seq: int
    _ws: websockets.ClientConnection | None
    _sock: socket.socket

    def __init__(self, guild_id: str, url: str, session_id: str, token: str, config: Config):
        self.url = f"wss://{url}?v=8"
        self.session_id = session_id
        self.token = token
        self.guild_id = guild_id
        self.config = config
        self._last_seq = -1

    async def send(self, op: VoiceOpCode, data: Any):
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_heartbeat(self, nonce: int):
        print(f">>> VOICE HEARTBEAT d = {self._last_seq}, nonce = {nonce}")
        await self.send(VoiceOpCode.HEARTBEAT, {"seq_ack": self._last_seq,
                                                "t": nonce})

    async def regular_heartbeats(self, heartbeat_interval: float):
        nonce = random.randint(1000000000000, 1999999999999)
        while True:
            await self.send_heartbeat(nonce)
            await asyncio.sleep(heartbeat_interval)
            nonce += 1

    async def identify(self):
        data = {"token": self.token,
                "server_id": self.guild_id,
                "user_id": self.config.application_id,
                "session_id": self.session_id,
                "max_dave_protocol_version": 0}
        print(">>> VOICE IDENFITY")
        await self.send(VoiceOpCode.IDENTIFY, data)

    async def handle_hello(self, event: VoiceEvent):
        print(f"<<< VOICE HELLO {event}")
        heartbeat_interval = event.get("heartbeat_interval") / 1000
        await self.identify()
        asyncio.create_task(self.regular_heartbeats(heartbeat_interval))

    def _ip_discovery_packet(self, ssrc: int) -> bytes:
        fmt = "!HHI" + 66 * "x"
        return struct.pack(fmt, 0x1, 70, ssrc)

    def handle_ready(self, event: VoiceEvent):
        print(f"<<< VOICE READY {event}")
        ip, port, ssrc = event.get("ip"), event.get("port"), event.get("ssrc")
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("0.0.0.0", 2917))
        self._sock.connect((ip, port))
        self._sock.send(self._ip_discovery_packet(ssrc))
        print(f">>> IP DISCOVERY TO {ip}:{port}")
        resp = self._sock.recvfrom(1024)
        print(f"<<< IP DISCOVERY RESPONSE {resp}")
        # TODO negotiate protocol

    async def receive_loop(self):
        while True:
            event = VoiceEvent(await self._ws.recv())
            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case VoiceOpCode.HELLO:
                    asyncio.create_task(self.handle_hello(event))
                case VoiceOpCode.HEARTBEAT_ACK:
                    print("<<< VOICE HEARTBEAT ACK")
                case VoiceOpCode.READY:
                    self.handle_ready(event)
                case _:
                    print(f"<<< VOICE UNKOWN {event}")

    async def start(self):
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except asyncio.exceptions.CancelledError:
            print("Closing voice...\n")
        finally:
            await self._ws.close()

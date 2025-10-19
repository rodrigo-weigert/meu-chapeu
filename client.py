import asyncio
import json
import random
import websockets

from event import Event, OpCode
from typing import Callable, Dict, Any
from config import Config
from voice_client import VoiceClient
from logs import logger as base_logger

logger = base_logger.bind(context="GatewayClient")


class Client:
    url: str
    intents: int
    config: Config
    _ws: websockets.ClientConnection
    _last_seq: int | None
    _interaction_handlers: Dict[str, Callable[[Event], Any]]
    _voice_state_updates: Dict[str, asyncio.Future[Event]]
    _voice_server_updates: Dict[str, asyncio.Future[Event]]
    _session_id: str
    _resume_url: str

    def __init__(self, url: str, intents: int, config: Config):
        self.url = url
        self._last_seq = None
        self.intents = intents
        self.config = config
        self._interaction_handlers = {}
        self._voice_state_updates = {}
        self._voice_server_updates = {}

    def register_interaction_handler(self, interaction_name: str, handler: Callable[[Event], Any]):
        self._interaction_handlers[interaction_name] = handler

    async def send(self, op: OpCode, data: Any):
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_heartbeat(self):
        logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}")
        await self.send(OpCode.HEARTBEAT, self._last_seq)

    async def regular_heartbeats(self, heartbeat_interval):
        while True:
            await self.send_heartbeat()
            await asyncio.sleep(heartbeat_interval)

    async def identify(self):
        data = {"token": self.config.api_token,
                "intents": self.intents,
                "properties": {"os": "linux",
                               "browser": "meu_chapeu",
                               "device": "meu_chapeu"}}
        logger.log("OUT", "IDENTIFY")
        await self.send(OpCode.IDENTIFY, data)

    async def handle_hello(self, event: Event):
        logger.log("IN", "HELLO")
        heartbeat_interval = event.get("heartbeat_interval") / 1000
        initial_wait = heartbeat_interval * random.random()
        logger.info(f"Heartbeat interval: {heartbeat_interval:.3f} s")
        logger.info(f"Will start regular heartbeats in {initial_wait:.3f} s")
        await self.identify()
        await asyncio.sleep(initial_wait)
        asyncio.create_task(self.regular_heartbeats(heartbeat_interval))

    def handle_voice_state_update(self, event: Event):
        if event.get("member")["user"]["id"] != self.config.application_id:
            return  # We receive updates for all guild users
        guild_id = event.get("guild_id")
        fut = self._voice_state_updates.pop(guild_id, None)
        if fut:
            fut.set_result(event)

    def handle_voice_server_update(self, event: Event):
        guild_id = event.get("guild_id")
        fut = self._voice_server_updates.pop(guild_id, None)
        if fut:
            fut.set_result(event)

    async def handle_dispatch(self, event: Event):
        logger.log("IN", f"DISPATCH: {event}")
        match event.name:
            case "READY":
                self._session_id = event.get("session_id")
                self._resume_url = event.get("resume_gateway_url")
            case "INTERACTION_CREATE":
                command_name = event.get("data")["name"]
                await self._interaction_handlers[command_name](event)
            case "VOICE_STATE_UPDATE":
                self.handle_voice_state_update(event)
            case "VOICE_SERVER_UPDATE":
                self.handle_voice_server_update(event)
            case "RESUMED":
                logger.info("Connection resumed successfully")

    async def join_voice_channel(self, guild_id: str, channel_id: str) -> VoiceClient:
        state_future = asyncio.get_running_loop().create_future()
        server_future = asyncio.get_running_loop().create_future()
        self._voice_state_updates[guild_id] = state_future
        self._voice_server_updates[guild_id] = server_future

        vsu_payload = {"guild_id": guild_id,
                       "channel_id": channel_id,
                       "self_mute": False,
                       "self_deaf": True}
        logger.log("OUT", f"VOICE_STATE_UPDATE: {vsu_payload}")
        await self.send(OpCode.VOICE_STATE_UPDATE, vsu_payload)

        # TODO handle timeouts
        state_resp = await state_future
        server_resp = await server_future

        vc = VoiceClient(guild_id,
                         server_resp.get("endpoint"),
                         state_resp.get("session_id"),
                         server_resp.get("token"),
                         self.config)

        logger.info(f"JOINED VOICE guild_id = {guild_id}, channel_id = {channel_id}")

        asyncio.create_task(vc.start())
        return vc

    async def handle_reconnect(self, event: Event):
        logger.log("IN", "RECONNECT")
        self._ws = await websockets.connect(self._resume_url)
        logger.log("OUT", f"RESUME session_id = {self._session_id}, seq = {self._last_seq}")
        await self.send(OpCode.RESUME, {"token": self.config.api_token,
                                        "session_id": self._session_id,
                                        "seq": self._last_seq})

    async def receive_loop(self):
        while True:
            event = Event(await self._ws.recv())
            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case OpCode.HELLO:
                    asyncio.create_task(self.handle_hello(event))
                case OpCode.HEARTBEAT_ACK:
                    logger.log("IN", "HEARTBEAT ACK")
                case OpCode.HEARTBEAT:
                    await self.send_heartbeat()
                case OpCode.DISPATCH:
                    asyncio.create_task(self.handle_dispatch(event))
                case OpCode.RECONNECT:
                    await self.handle_reconnect(event)
                case OpCode.INVALID_SESSION:
                    logger.log("IN", "INVALID SESSION")
                    logger.info("Received invalid session, exiting")
                    break

    async def start(self):
        logger.info("Bot starting")
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except asyncio.exceptions.CancelledError:
            pass
        finally:
            await self._ws.close()

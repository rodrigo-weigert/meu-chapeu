import asyncio
import json
import random
import websockets

from event import Event, OpCode
from typing import Callable, Dict, Any
from config import Config
from logs import logger as base_logger

logger = base_logger.bind(context="GatewayClient")


class Client:
    url: str
    intents: int
    config: Config
    _ws: websockets.ClientConnection | None
    _last_seq: int | None
    _interaction_handlers: Dict[str, Callable[[Event], Any]]
    _voice_state_updates: Dict[str, asyncio.Future[Event]]
    _voice_server_updates: Dict[str, asyncio.Future[Event]]

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
            case "INTERACTION_CREATE":
                command_name = event.get("data")["name"]
                await self._interaction_handlers[command_name](event)
            case "VOICE_STATE_UPDATE":
                self.handle_voice_state_update(event)
            case "VOICE_SERVER_UPDATE":
                self.handle_voice_server_update(event)

    async def prepare_join_voice(self, guild_id: str, channel_id: str) -> dict[str, str]:
        state_future = asyncio.get_running_loop().create_future()
        server_future = asyncio.get_running_loop().create_future()
        self._voice_state_updates[guild_id] = state_future
        self._voice_server_updates[guild_id] = server_future

        logger.log("OUT", "VOICE_STATE_UPDATE")
        await self.send(OpCode.VOICE_STATE_UPDATE, {"guild_id": guild_id,
                                                    "channel_id": channel_id,
                                                    "self_mute": False,
                                                    "self_deaf": True})

        voice_state_update = await state_future
        voice_server_update = await server_future

        result = {"endpoint": voice_server_update.get("endpoint"),
                  "token": voice_server_update.get("token"),
                  "session_id": voice_state_update.get("session_id")}
        logger.info(f"*** JOIN VOICE READY {result}")
        return result

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

    async def _start(self):
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await self._ws.close()

    def start(self):
        asyncio.run(self._start())

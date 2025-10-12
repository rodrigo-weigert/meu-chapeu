import asyncio
import json
import random
import websockets

from event import Event, OpCode
from typing import Callable, Dict, Any

class Client:
    url: str
    intents: int
    _token: str
    _last_seq: int | None
    _interaction_handlers: Dict[str, Callable[[Event], Any]]

    def __init__(self, url, intents, token):
        self.url = url
        self._last_seq = None
        self.intents = intents
        self._token = token
        self._interaction_handlers = {}

    def register_interaction_handler(self, interaction_name: str, handler: Callable[[Event], Any]):
        self._interaction_handlers[interaction_name] = handler

    async def send(self, op, data):
        payload = {"op": op, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_heartbeat(self):
        print(f">>> HEARTBEAT d = {self._last_seq}")
        await self.send(1, self._last_seq)

    async def regular_heartbeats(self, heartbeat_interval):
        while True:
            await self.send_heartbeat()
            await asyncio.sleep(heartbeat_interval)

    async def identify(self):
        data = {"token": self._token,
                "intents": self.intents,
                "properties": {"os": "linux",
                               "browser": "meu_chapeu",
                               "device": "meu_chapeu"}}
        print(">>> IDENFITY")
        await self.send(2, data)


    async def handle_hello(self, event: Event):
        print("<<< HELLO")
        heartbeat_interval = event.get("heartbeat_interval") / 1000
        initial_wait = heartbeat_interval * random.random()
        print(f"*** Heartbeat interval: {heartbeat_interval:.3f} s")
        print(f"*** Will start regular heartbeats in {initial_wait:.3f} s")
        await asyncio.sleep(initial_wait)
        asyncio.create_task(self.regular_heartbeats(heartbeat_interval))
        await self.identify()

    async def handle_dispatch(self, event: Event):
        print(f"<<< DISPATCH: {event}")
        if event.name == "INTERACTION_CREATE":
            data = event.get("data")
            command_name = data["name"]
            self._interaction_handlers[command_name](event)

    
    async def receive_loop(self):
        while True:
            event = Event(await self._ws.recv())
            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case OpCode.HELLO:
                    asyncio.create_task(self.handle_hello(event))
                case OpCode.HEARTBEAT_ACK:
                    print("<<< HEARTBEAT ACK")
                case OpCode.HEARTBEAT:
                    await self.send_heartbeat()
                case OpCode.DISPATCH:
                    asyncio.create_task(self.handle_dispatch(event))

    async def _start(self):
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except asyncio.exceptions.CancelledError:
            print("Closing...\n")
        finally:
            await self._ws.close()

    def start(self):
        asyncio.run(self._start())

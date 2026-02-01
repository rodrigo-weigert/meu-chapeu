import asyncio
import json
import random
import websockets
import youtube

from event import Event, OpCode
from typing import Dict, Any
from config import Config
from voice_client import VoiceClient
from http_client import HttpClient
from logs import logger as base_logger

logger = base_logger.bind(context="GatewayClient")


ALLOWED_RECONNECT_CLOSE_CODES = {1001, 1006, 4000, 4001, 4002, 4003, 4005, 4007, 4008, 4009}


class Client:
    http_client: HttpClient
    url: str
    intents: int
    config: Config
    voice_clients: Dict[str, VoiceClient]
    _ws: websockets.ClientConnection
    _last_seq: int | None
    _voice_state_updates: Dict[str, asyncio.Future[Event]]
    _voice_server_updates: Dict[str, asyncio.Future[Event]]
    _session_id: str
    _resume_url: str
    _identified: bool
    _closed: bool
    _heartbeat_task: asyncio.Task | None

    def __init__(self, http_client: HttpClient, intents: int, config: Config):
        self.url = http_client.get_gateway_url()
        self.http_client = http_client
        self._last_seq = None
        self.intents = intents
        self.config = config
        self.voice_clients = {}
        self._voice_state_updates = {}
        self._voice_server_updates = {}
        self._identified = False
        self._closed = False

    async def send(self, op: OpCode, data: Any):
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def send_heartbeat(self):
        try:
            await self.send(OpCode.HEARTBEAT, self._last_seq)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Could not send heartbeat: connection is closed (reconnecting?)")
            return
        logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}")

    async def regular_heartbeats(self, heartbeat_interval):
        try:
            while not self._closed:
                await self.send_heartbeat()
                await asyncio.sleep(heartbeat_interval)
        except asyncio.exceptions.CancelledError:
            logger.info("Heartbeat task cancelled")

    async def identify(self):
        data = {"token": self.config.api_token,
                "intents": self.intents,
                "properties": {"os": "linux",
                               "browser": "meu_chapeu",
                               "device": "meu_chapeu"}}
        await self.send(OpCode.IDENTIFY, data)
        logger.log("OUT", "IDENTIFY")

    async def handle_hello(self, event: Event):
        logger.log("IN", "HELLO")

        if self._identified:
            return

        heartbeat_interval = event.get("heartbeat_interval") / 1000
        initial_wait = heartbeat_interval * random.random()
        logger.info(f"Heartbeat interval: {heartbeat_interval:.3f} s")
        logger.info(f"Will start regular heartbeats in {initial_wait:.3f} s")
        await self.identify()
        await asyncio.sleep(initial_wait)
        self._heartbeat_task = asyncio.create_task(self.regular_heartbeats(heartbeat_interval))

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

    async def handle_play(self, event: Event):
        guild_id = event.get("guild_id")
        user_id = event.get("member")["user"]["id"]

        response_ok = self.http_client.respond_interaction_with_message(event, "", deferred=True)
        if not response_ok:
            return

        channel_id = self.http_client.get_user_voice_channel(guild_id, user_id)
        if channel_id is None:
            self.http_client.update_original_interaction_response(event, "You need to be in a channel I can join or have already joined, in the same server you called me.")
            return

        voice_client = self.voice_clients.get(guild_id)

        if voice_client is None or voice_client.closed:
            voice_client = await self.join_voice_channel(guild_id, channel_id)
            self.voice_clients[guild_id] = voice_client
        elif voice_client.channel_id != channel_id:
            self.http_client.update_original_interaction_response(event, "You need to be in the same channel and server I'm currently connected to")
            return

        search_query = event.get("data")["options"][0]["value"]
        media = youtube.get_video_from_user_query(search_query, self.config)

        if media is None:
            self.http_client.update_original_interaction_response(event, "Failed to find video. If you provided a link, it may be incorrect. If you used a search query, it may have returned no results.")
            return

        response_ok = self.http_client.update_original_interaction_response(event, f"Adding [{media.title}]({media.link}) ({media.duration_str()}) to the queue")
        if response_ok:
            await voice_client.enqueue_media(media)

    def handle_skip(self, event: Event):
        guild_id = event.get("guild_id")
        user_id = event.get("member")["user"]["id"]
        voice_client = self.voice_clients.get(guild_id)

        if voice_client is None:
            self.http_client.respond_interaction_with_message(event, "I'm not connected in this server", ephemeral=True)
            return
        elif voice_client.channel_id != self.http_client.get_user_voice_channel(guild_id, user_id):
            self.http_client.respond_interaction_with_message(event, "You need to be in the same channel I'm currently connected to", ephemeral=True)
            return

        if voice_client.skip_current_media():
            self.http_client.respond_interaction_with_message(event, "Skipped")
        else:
            self.http_client.respond_interaction_with_message(event, "Nothing to skip", ephemeral=True)

    async def handle_dispatch(self, event: Event):
        logger.log("IN", f"DISPATCH: {event}")
        match event.name:
            case "READY":
                self._session_id = event.get("session_id")
                self._resume_url = event.get("resume_gateway_url")
                self._identified = True
            case "INTERACTION_CREATE":
                command_name = event.get("data")["name"]
                match command_name:
                    case "play":
                        await self.handle_play(event)
                    case "skip":
                        self.handle_skip(event)

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
                         channel_id,
                         server_resp.get("endpoint"),
                         state_resp.get("session_id"),
                         server_resp.get("token"),
                         lambda: self.leave_voice_channel(guild_id),
                         self.config)

        logger.info(f"JOINED VOICE guild_id = {guild_id}, channel_id = {channel_id}")

        asyncio.create_task(vc.start())
        return vc

    async def leave_voice_channel(self, guild_id: str) -> None:
        vsu_payload = {"guild_id": guild_id,
                       "channel_id": None,
                       "self_mute": False,
                       "self_deaf": True}
        try:
            await self.send(OpCode.VOICE_STATE_UPDATE, vsu_payload)
        except websockets.exceptions.ConnectionClosed:
            return

        logger.log("OUT", f"VOICE_STATE_UPDATE: {vsu_payload}")

    async def reconnect(self):
        logger.info("Reconnecting...")
        connected = False

        while not connected:
            try:
                self._ws = await websockets.connect(self._resume_url, open_timeout=None)
                connected = True
            except Exception as e:
                logger.warning(f"Exception: {e}")
                logger.warning("Reconnection failed, retrying after 30 seconds...")
                await asyncio.sleep(30)

        await self.send(OpCode.RESUME, {"token": self.config.api_token,
                                        "session_id": self._session_id,
                                        "seq": self._last_seq})
        logger.log("OUT", f"RESUME session_id = {self._session_id}, seq = {self._last_seq}")

    async def handle_invalid_session(self):
        logger.info("Received invalid session, opening new session in 60 seconds")

        self._identified = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

        connected = False
        while not connected:
            await asyncio.sleep(60)
            logger.info("Attempting to start a new session...")
            try:
                self._ws = await websockets.connect(self.url, open_timeout=None)
                connected = True
            except Exception as e:
                logger.warning(f"Attempt to start new session failed. Exception: {e}")

        logger.info("New session started")

    async def receive_loop(self):
        while True:
            try:
                event = Event(await self._ws.recv())
            except websockets.exceptions.ConnectionClosedOK as e:
                logger.info(f"Connection normal closure (close code: {e.code}, reason: {e.reason})")
                if e.code in ALLOWED_RECONNECT_CLOSE_CODES:
                    await self.reconnect()
                    continue
                else:
                    logger.info(f"Close code {e.code} does not allow reconnection, stopping client")
                    return
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"Connection closed with error (close code: {e.code}, reason: {e.reason})")
                if e.code in ALLOWED_RECONNECT_CLOSE_CODES:
                    await self.reconnect()
                    continue
                else:
                    logger.warning(f"Close code {e.code} does not allow reconnection, stopping client")
                    return

            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case OpCode.HELLO:
                    asyncio.create_task(self.handle_hello(event))
                case OpCode.HEARTBEAT_ACK:
                    logger.log("IN", "HEARTBEAT ACK")  # TODO: handle lack of heartbeat ack (zombie connection)
                case OpCode.HEARTBEAT:
                    await self.send_heartbeat()
                case OpCode.DISPATCH:
                    asyncio.create_task(self.handle_dispatch(event))
                case OpCode.RECONNECT:
                    logger.log("IN", "RECONNECT")
                    await self.reconnect()
                case OpCode.INVALID_SESSION:
                    logger.log("IN", f"INVALID SESSION {event}")
                    await self.handle_invalid_session()

    async def start(self):
        logger.info("Bot starting")
        self._ws = await websockets.connect(self.url)
        try:
            await self.receive_loop()
        except asyncio.exceptions.CancelledError:
            logger.info("Receive loop task cancelled")
        finally:
            self._closed = True
            await self._ws.close()

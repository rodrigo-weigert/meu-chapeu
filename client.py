from arguments import args
from dataclasses import dataclass, field
from enum import IntEnum, unique
import asyncio
import http_client
import json
import random
import websockets
import youtube

from typing import Dict, Any, Set
from config import config
from voice_client import VoiceClient
from logs import logger as base_logger
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

logger = base_logger.bind(context="GatewayClient")


@unique
class _OpCode(IntEnum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


class _Event:
    _opcode: _OpCode
    _seq_num: int | None
    _name: str | None
    _parsed: Dict[str, Any]

    def __init__(self, raw: str) -> None:
        parsed = json.loads(raw)
        self._opcode = _OpCode(parsed["op"])
        self._seq_num = parsed.get("s")
        self._name = parsed.get("t")
        self._parsed = parsed["d"]

    @property
    def opcode(self) -> _OpCode:
        return self._opcode

    @property
    def seq_num(self) -> int | None:
        return self._seq_num

    @property
    def name(self) -> str | None:
        return self._name

    def __getitem__(self, key: str) -> Any:
        return self._parsed[key]

    def __contains__(self, key: str) -> bool:
        return key in self._parsed

    def __str__(self) -> str:
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Name: {self.name}, Data: {self._parsed}"


@dataclass(frozen=True)
class UserInteraction:
    name: str
    id: str
    token: str = field(repr=False)
    guild_id: str
    user_id: str
    username: str
    options: Dict[str, str]

    @staticmethod
    def _parse_options(event: _Event) -> Dict[str, str]:
        if "options" in event["data"]:
            return {option["name"]: option["value"] for option in event["data"]["options"]}
        return {}

    @classmethod
    def _from_event(cls, event: _Event) -> "UserInteraction":
        return UserInteraction(
                name=event["data"]["name"],
                guild_id=event["guild_id"],
                user_id=event["member"]["user"]["id"],
                username=event["member"]["user"]["username"],
                id=event["id"],
                token=event["token"],
                options=cls._parse_options(event),
        )


class Client:
    _url: str
    _intents: int
    _last_seq: int | None
    _voice_clients: Dict[str, VoiceClient]
    _voice_state_updates: Dict[str, asyncio.Future[_Event]]
    _voice_server_updates: Dict[str, asyncio.Future[_Event]]
    _identified: bool
    _closed: bool
    _waiting_heartbeat_ack: bool
    _ws: websockets.ClientConnection
    _session_id: str
    _resume_url: str
    _heartbeat_task: asyncio.Task | None

    def __init__(self, intents: int) -> None:
        self._url = http_client.get_gateway_url()
        self._intents = intents

        self._last_seq = None
        self._voice_clients = {}
        self._voice_state_updates = {}
        self._voice_server_updates = {}
        self._identified = False
        self._closed = False
        self._waiting_heartbeat_ack = False

    async def start(self) -> None:
        logger.info("Bot starting")
        self._ws = await websockets.connect(self._url)
        try:
            await self._receive_loop()
        except asyncio.exceptions.CancelledError:
            logger.info("Receive loop task cancelled")
        finally:
            self._closed = True
            await self._ws.close()

    async def _send(self, op: _OpCode, data: Any) -> None:
        payload = {"op": op.value, "d": data}
        await self._ws.send(json.dumps(payload))

    async def _send_heartbeat(self) -> None:
        if self._waiting_heartbeat_ack:
            logger.warning("Last heartbeat was not acknowledged")
        try:
            self._waiting_heartbeat_ack = True
            await self._send(_OpCode.HEARTBEAT, self._last_seq)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Could not send heartbeat: connection is closed (reconnecting?)")
            self._waiting_heartbeat_ack = False
            return
        if args.log_heartbeats:
            logger.log("OUT", f"HEARTBEAT last_seq = {self._last_seq}")

    def _handle_heartbeat_ack(self):
        self._waiting_heartbeat_ack = False
        if args.log_heartbeats:
            logger.log("IN", "HEARTBEAT ACK")

    async def _regular_heartbeats(self, heartbeat_interval) -> None:
        try:
            while not self._closed:
                await self._send_heartbeat()
                await asyncio.sleep(heartbeat_interval)
        except asyncio.exceptions.CancelledError:
            logger.info("Heartbeat task cancelled")

    async def _identify(self) -> None:
        data = {"token": config.api_token,
                "intents": self._intents,
                "properties": {"os": "linux",
                               "browser": "meu_chapeu",
                               "device": "meu_chapeu"}}
        await self._send(_OpCode.IDENTIFY, data)
        logger.log("OUT", "IDENTIFY")

    async def _handle_hello(self, event: _Event) -> None:
        logger.log("IN", "HELLO")

        if self._identified:
            return

        heartbeat_interval = event["heartbeat_interval"] / 1000
        initial_wait = heartbeat_interval * random.random()
        logger.info(f"Heartbeat interval: {heartbeat_interval:.3f} s")
        logger.info(f"Will start regular heartbeats in {initial_wait:.3f} s")
        await self._identify()
        await asyncio.sleep(initial_wait)
        self._heartbeat_task = asyncio.create_task(self._regular_heartbeats(heartbeat_interval))

    def _handle_user_voice_state_update(self, event: _Event) -> None:
        username = event["member"]["user"]["username"]
        relevant_fields = {field: event[field] for field in ["self_mute", "self_deaf", "self_stream", "guild_id", "channel_id", "user_id"] if field in event}

        logger.log("IN", f"DISPATCH - USER VOICE STATE UPDATE ({username}): {relevant_fields}")

    def _handle_voice_state_update(self, event: _Event) -> None:
        if event["member"]["user"]["id"] != config.application_id:
            self._handle_user_voice_state_update(event)
            return

        logger.log("IN", f"DISPATCH - BOT VOICE STATE UPDATE: {event}")

        guild_id = event["guild_id"]
        fut = self._voice_state_updates.pop(guild_id, None)
        if fut:
            fut.set_result(event)

    def _handle_voice_server_update(self, event: _Event) -> None:
        logger.log("IN", f"DISPATCH - VOICE SERVER UPDATE: {event}")

        guild_id = event["guild_id"]
        fut = self._voice_server_updates.pop(guild_id, None)
        if fut:
            fut.set_result(event)

    async def _handle_play(self, interaction: UserInteraction) -> None:
        media_task = asyncio.create_task(youtube.get_video_from_user_query(interaction.options["query"]))

        channel_id = await http_client.get_user_voice_channel(interaction.guild_id, interaction.user_id)

        if channel_id is None:
            media_task.cancel()
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in a channel I can join or have already joined, in the same server you called me.", ephemeral=True)
            return

        voice_client = self._voice_clients.get(interaction.guild_id)

        if voice_client is None or voice_client.closed:
            voice_client = await self._join_voice_channel(interaction.guild_id, channel_id)
            self._voice_clients[interaction.guild_id] = voice_client
        elif voice_client.channel_id != channel_id:
            media_task.cancel()
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in the same channel and server I'm currently connected to", ephemeral=True)
            return

        media = await media_task
        if media is None:
            await http_client.respond_interaction(interaction.id, interaction.token, "Failed to find video. If you provided a link, it may be incorrect. If you used a search query, it may have returned no results.", ephemeral=True)
            return

        asyncio.create_task(http_client.respond_interaction(interaction.id, interaction.token, f"Adding [{media.title}]({media.link}) ({media.duration_str()}) to the queue"))
        await voice_client.enqueue_media(media)

    async def _handle_skip(self, interaction: UserInteraction) -> None:
        voice_client = self._voice_clients.get(interaction.guild_id)

        if voice_client is None or voice_client.closed:
            await http_client.respond_interaction(interaction.id, interaction.token, "I'm not connected in this server", ephemeral=True)
            return
        elif voice_client.channel_id != await http_client.get_user_voice_channel(interaction.guild_id, interaction.user_id):
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in the same channel I'm currently connected to", ephemeral=True)
            return

        if voice_client.skip_current_media():
            await http_client.respond_interaction(interaction.id, interaction.token, "Skipped")
        else:
            await http_client.respond_interaction(interaction.id, interaction.token, "Nothing to skip", ephemeral=True)

    async def _handle_interaction(self, event: _Event) -> None:
        interaction = UserInteraction._from_event(event)
        logger.log("IN", f"<green><b>NEW INTERACTION</b></green>: {interaction}")

        match interaction.name:
            case "play":
                await self._handle_play(interaction)
            case "skip":
                await self._handle_skip(interaction)

    async def _handle_dispatch(self, event: _Event) -> None:
        match event.name:
            case "READY":
                logger.log("IN", f"DISPATCH - READY: {event}")
                self._session_id = event["session_id"]
                self._resume_url = event["resume_gateway_url"]
                self._identified = True
            case "INTERACTION_CREATE":
                await self._handle_interaction(event)
            case "VOICE_STATE_UPDATE":
                self._handle_voice_state_update(event)
            case "VOICE_SERVER_UPDATE":
                self._handle_voice_server_update(event)
            case "RESUMED":
                logger.log("IN", f"DISPATCH - RESUMED: {event}")

    async def _join_voice_channel(self, guild_id: str, channel_id: str) -> VoiceClient:
        state_future = asyncio.get_running_loop().create_future()
        server_future = asyncio.get_running_loop().create_future()
        self._voice_state_updates[guild_id] = state_future
        self._voice_server_updates[guild_id] = server_future

        vsu_payload = {"guild_id": guild_id,
                       "channel_id": channel_id,
                       "self_mute": False,
                       "self_deaf": True}
        logger.log("OUT", f"VOICE_STATE_UPDATE: {vsu_payload}")
        await self._send(_OpCode.VOICE_STATE_UPDATE, vsu_payload)

        # TODO handle timeouts
        state_resp = await state_future
        server_resp = await server_future

        vc = VoiceClient(guild_id,
                         channel_id,
                         server_resp["endpoint"],
                         state_resp["session_id"],
                         server_resp["token"],
                         lambda: self._leave_voice_channel(guild_id))

        logger.info(f"JOINED VOICE guild_id = {guild_id}, channel_id = {channel_id}")

        asyncio.create_task(vc.start())
        return vc

    async def _leave_voice_channel(self, guild_id: str) -> None:
        vsu_payload = {"guild_id": guild_id,
                       "channel_id": None,
                       "self_mute": False,
                       "self_deaf": True}
        try:
            await self._send(_OpCode.VOICE_STATE_UPDATE, vsu_payload)
        except websockets.exceptions.ConnectionClosed:
            return

        logger.log("OUT", f"VOICE_STATE_UPDATE: {vsu_payload}")

    async def _reconnect(self) -> None:
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

        await self._send(_OpCode.RESUME, {"token": config.api_token,
                                          "session_id": self._session_id,
                                          "seq": self._last_seq})
        logger.log("OUT", f"RESUME session_id = {self._session_id}, seq = {self._last_seq}")

    async def _handle_invalid_session(self) -> None:
        logger.info("Received invalid session, opening new session in 60 seconds")

        self._identified = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

        connected = False
        while not connected:
            await asyncio.sleep(60)
            logger.info("Attempting to start a new session...")
            try:
                self._ws = await websockets.connect(self._url, open_timeout=None)
                connected = True
            except Exception as e:
                logger.warning(f"Attempt to start new session failed. Exception: {e}")

        logger.info("New session started")

    async def _handle_disconnection(self, exception: ConnectionClosed) -> bool:
        if isinstance(exception, ConnectionClosedOK):
            logger.info(f"Connection closed (OK): {exception}")
        else:
            logger.warning(f"Connection closed (error): {exception}")
        if self._should_reconnect(exception):
            await self._reconnect()
            return True
        return False

    async def _receive_loop(self) -> None:
        while True:
            try:
                data = await self._ws.recv()
                assert isinstance(data, str)
                event = _Event(data)
            except ConnectionClosed as e:
                if await self._handle_disconnection(e):
                    continue
                else:
                    logger.info("Reconnection is not allowed. Closing client.")
                    return

            if event.seq_num:
                self._last_seq = event.seq_num
            match event.opcode:
                case _OpCode.HELLO:
                    asyncio.create_task(self._handle_hello(event))
                case _OpCode.HEARTBEAT_ACK:
                    self._handle_heartbeat_ack()
                case _OpCode.HEARTBEAT:
                    await self._send_heartbeat()
                case _OpCode.DISPATCH:
                    asyncio.create_task(self._handle_dispatch(event))
                case _OpCode.RECONNECT:
                    logger.log("IN", "RECONNECT")
                    await self._reconnect()
                case _OpCode.INVALID_SESSION:
                    logger.log("IN", f"INVALID SESSION {event}")
                    await self._handle_invalid_session()

    _ALLOWED_RECONNECT_CLOSE_CODES: Set[int] = {1001, 1006, 4000, 4001, 4002, 4003, 4005, 4007, 4008, 4009}

    @classmethod
    def _should_reconnect(cls, exception: ConnectionClosed) -> bool:
        return exception.rcvd is None or exception.rcvd.code in cls._ALLOWED_RECONNECT_CLOSE_CODES

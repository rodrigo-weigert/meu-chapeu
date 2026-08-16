import asyncio
import http_client
import media_fetcher
import interactions

from interactions import InteractionFlag, TextComponent, ThumbnailComponent, ContainerComponent, SectionComponent
from client import UserInteraction, UserInteractionHandler, VoiceService
from voice_client import VoiceClient
from media_file import MediaFile
from logs import logger as base_logger
from typing import Dict, Any


class _MusicSession:
    _media_queue: asyncio.Queue
    _vc: VoiceClient
    _closed: bool
    _task: asyncio.Task

    def __init__(self, voice_client: VoiceClient) -> None:
        self._media_queue = asyncio.Queue()
        self._vc = voice_client
        self._closed = False
        self._task = asyncio.create_task(self._start())

        self._logger = base_logger.bind(context=f"MusicSession:{voice_client.guild_id}")

    def close(self) -> None:
        self._closed = True
        self._task.cancel()

    @property
    def channel_id(self) -> str:
        return self._vc.channel_id

    def add_to_queue(self, media_file: MediaFile) -> None:
        self._ensure_not_closed()

        self._logger.info(f"Adding media {media_file.title} to the queue")
        self._media_queue.put_nowait(media_file)

    def skip_current(self) -> bool:
        self._ensure_not_closed()

        skipped = self._vc.skip_current_audio()
        if skipped:
            self._logger.info("Skipped current media")
        else:
            self._logger.info("Nothing to skip")
        return skipped

    async def _start(self) -> None:
        self._logger.info("Starting music session")
        await self._session_loop()

    def _ensure_not_closed(self) -> None:
        if self._closed:
            raise Exception("Music session is closed")

    async def _session_loop(self) -> None:
        try:
            while not self._vc.closed:
                self._logger.info("Waiting for next media")
                media_file = await self._media_queue.get()

                await self._vc.play_audio(media_file)
        except asyncio.CancelledError:
            pass
        self._logger.info("Session closed")
        self._closed = True


def build_string_response(message: str) -> Dict[str, Any]:
    return interactions.build_string_response(message, InteractionFlag.SUPPRESS_EMBEDS)


def build_error_response(message: str) -> Dict[str, Any]:
    return interactions.build_string_response(message, InteractionFlag.EPHEMERAL)


def build_media_response(media: MediaFile, user_id: str) -> Dict[str, Any]:
    c = ContainerComponent([SectionComponent([
           TextComponent(f"### [{media.title}]({media.link})"),
           TextComponent(f"**Duration:** {media.duration_str()}")],
            accessory=ThumbnailComponent(media.thumbnail))])
    return interactions.build_component_response([c], InteractionFlag.SUPPRESS_EMBEDS | InteractionFlag.IS_COMPONENTS_V2)


CHANNEL_NOT_FOUND_RESPONSE = build_error_response("You need to be in a channel I can join or have already joined, in the same server you called me.")
WRONG_CHANNEL_RESPONSE = build_error_response("You need to be in the same channel I'm currently connected to")
MEDIA_NOT_FOUND_RESPONSE = build_error_response("Failed to find video. If you provided a link, it may be incorrect. If you used a search query, it may have returned no results.")
NOTHING_TO_SKIP_RESPONSE = build_error_response("Nothing to skip")
NO_SESSION_RESPONSE = build_error_response("I'm not connected in this server")
SKIP_SUCCESSFUL_RESPONSE = build_string_response("Skipped")


class MusicPlayerBot(UserInteractionHandler):
    _sessions: Dict[str, _MusicSession]

    def __init__(self):
        self._sessions = {}

    async def handle_interaction(self, interaction: UserInteraction, voice_service: VoiceService) -> None:
        match interaction.name:
            case "play":
                await self._handle_play(interaction, voice_service)
            case "skip":
                await self._handle_skip(interaction)

    def _remove_session(self, guild_id: str) -> None:
        session = self._sessions.pop(guild_id)
        session.close()

    async def _create_session(self, guild_id: str, channel_id: str, voice_service: VoiceService) -> _MusicSession:
        voice_client = await voice_service.join_voice_channel(guild_id, channel_id, lambda: self._remove_session(guild_id))
        session = _MusicSession(voice_client)
        self._sessions[guild_id] = session
        return session

    async def _handle_play(self, interaction: UserInteraction, voice_service: VoiceService) -> None:
        guild_id = interaction.guild_id
        media_task = asyncio.create_task(media_fetcher.fetch_media_for_query(interaction.options["query"]))

        channel_id = await http_client.get_user_voice_channel(guild_id, interaction.user_id)

        if channel_id is None:
            media_task.cancel()
            await interaction.respond(CHANNEL_NOT_FOUND_RESPONSE)
            return

        session = self._sessions.get(guild_id)

        if session is None:
            session = await self._create_session(guild_id, channel_id, voice_service)
        elif session.channel_id != channel_id:
            media_task.cancel()
            await interaction.respond(WRONG_CHANNEL_RESPONSE)
            return

        media = await media_task
        if media is None:
            await interaction.respond(MEDIA_NOT_FOUND_RESPONSE)
            return

        asyncio.create_task(interaction.respond(build_media_response(media, interaction.user_id)))
        asyncio.get_running_loop().run_in_executor(None, media.download)
        session.add_to_queue(media)

    async def _handle_skip(self, interaction: UserInteraction) -> None:
        session = self._sessions.get(interaction.guild_id)

        if session is None:
            await interaction.respond(NO_SESSION_RESPONSE)
            return
        elif session.channel_id != await http_client.get_user_voice_channel(interaction.guild_id, interaction.user_id):
            await interaction.respond(WRONG_CHANNEL_RESPONSE)
            return

        if session.skip_current():
            await interaction.respond(SKIP_SUCCESSFUL_RESPONSE)
        else:
            await interaction.respond(NOTHING_TO_SKIP_RESPONSE)

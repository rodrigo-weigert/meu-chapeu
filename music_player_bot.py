import asyncio
import http_client
import youtube

from client import UserInteraction, UserInteractionHandler, VoiceService


class MusicPlayerBot(UserInteractionHandler):
    async def handle_interaction(self, interaction: UserInteraction, voice_service: VoiceService) -> None:
        match interaction.name:
            case "play":
                await self._handle_play(interaction, voice_service)
            case "skip":
                await self._handle_skip(interaction, voice_service)

    async def _handle_play(self, interaction: UserInteraction, voice_service: VoiceService) -> None:
        media_task = asyncio.create_task(youtube.get_video_from_user_query(interaction.options["query"]))

        channel_id = await http_client.get_user_voice_channel(interaction.guild_id, interaction.user_id)

        if channel_id is None:
            media_task.cancel()
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in a channel I can join or have already joined, in the same server you called me.", ephemeral=True)
            return

        voice_client = await voice_service.join_voice_channel(interaction.guild_id, channel_id)

        if voice_client is None:
            media_task.cancel()
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in the same channel and server I'm currently connected to", ephemeral=True)
            return

        media = await media_task
        if media is None:
            await http_client.respond_interaction(interaction.id, interaction.token, "Failed to find video. If you provided a link, it may be incorrect. If you used a search query, it may have returned no results.", ephemeral=True)
            return

        asyncio.create_task(http_client.respond_interaction(interaction.id, interaction.token, f"Adding [{media.title}]({media.link}) ({media.duration_str()}) to the queue"))
        await voice_client.enqueue_media(media)

    async def _handle_skip(self, interaction: UserInteraction, voice_service: VoiceService) -> None:
        voice_client = voice_service.get_connected_voice_client(interaction.guild_id)

        if voice_client is None:
            await http_client.respond_interaction(interaction.id, interaction.token, "I'm not connected in this server", ephemeral=True)
            return
        elif voice_client.channel_id != await http_client.get_user_voice_channel(interaction.guild_id, interaction.user_id):
            await http_client.respond_interaction(interaction.id, interaction.token, "You need to be in the same channel I'm currently connected to", ephemeral=True)
            return

        if voice_client.skip_current_media():
            await http_client.respond_interaction(interaction.id, interaction.token, "Skipped")
        else:
            await http_client.respond_interaction(interaction.id, interaction.token, "Nothing to skip", ephemeral=True)

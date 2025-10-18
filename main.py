#!/usr/bin/env python3

import asyncio
import commands
import youtube

from client import Client
from intents import Intent
from config import Config
from http_client import HttpClient
from voice_client import VoiceClient


def main():
    config = Config()
    http_client = HttpClient(config)
    # http_client.create_slash_command(commands.Play)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config)

    async def handle_play(event):
        guild_id = event.get("guild_id")
        user_id = event.get("member")["user"]["id"]
        channel_id = http_client.get_user_voice_channel(guild_id, user_id)
        search_query = event.get("data")["options"][0]["value"]

        if channel_id is None:
            http_client.respond_interaction_with_message(event, "You are not in a valid channel I can join", ephemeral=True)
            return

        http_client.respond_interaction_with_message(event, "OK. Downloading and joining channel...")
        file_path = youtube.search_and_download_first(search_query)

        voice_session_data = await client.prepare_join_voice(guild_id, channel_id)
        voice_client = VoiceClient(guild_id, voice_session_data["endpoint"], voice_session_data["session_id"], voice_session_data["token"], file_path, config)
        await voice_client.start()

    client.register_interaction_handler("play", handle_play)
    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:  # Python <= 3.10
        pass


main()

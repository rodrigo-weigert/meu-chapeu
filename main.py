#!/usr/bin/env python3

import asyncio
import commands
import youtube

from client import Client
from intents import Intent
from config import Config
from http_client import HttpClient
from concurrent.futures import ThreadPoolExecutor

voice_client = None
song_task = None


def main():
    config = Config()
    http_client = HttpClient(config)
    # http_client.create_slash_command(commands.Play)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config)
    executor = ThreadPoolExecutor()

    async def handle_play(event):
        global voice_client
        global song_task

        if song_task is not None and not song_task.done():
            http_client.respond_interaction_with_message(event, "Ignoring because a song is already being played!", ephemeral=True)
            return

        guild_id = event.get("guild_id")
        user_id = event.get("member")["user"]["id"]
        channel_id = http_client.get_user_voice_channel(guild_id, user_id)
        search_query = event.get("data")["options"][0]["value"]

        http_client.respond_interaction_with_message(event, "Loading...", deferred=True)

        if voice_client is None or voice_client.closed:
            if channel_id is None:
                http_client.update_original_interaction_response(event, "You need to be in a channel I can join or have already joined, in the same server you called me.")
                return
            else:
                voice_client = await client.join_voice_channel(guild_id, channel_id)
        elif voice_client.channel_id != channel_id:
            http_client.update_original_interaction_response(event, "You need to be in the same channel and server I'm currently connected to", ephemeral=True)
            return

        media = youtube.get_video_from_user_query(search_query, config)
        if media is None:
            http_client.update_original_interaction_response(event, "Failed to get video metadata", ephemeral=True)
            return

        http_client.update_original_interaction_response(event, f"Playing [{media.title}]({media.link}) ({media.duration_str()})")

        download_success = await asyncio.get_running_loop().run_in_executor(executor, media.download)
        if download_success:
            song_task = asyncio.create_task(voice_client.play_song(media.file_path))

    client.register_interaction_handler("play", handle_play)
    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:  # Python <= 3.10
        pass


main()

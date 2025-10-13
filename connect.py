#!/usr/bin/env python3

from client import Client
from intents import Intent
from config import Config
from http_client import HttpClient
from voice_client import VoiceClient
import commands

TEST_GUILD_ID = "1426905746842583053"
TEST_CHANNEL_ID = "1426905748150947885"
MY_USER_ID = "301168289571274752"


def main():
    config = Config()
    http_client = HttpClient(config)
    http_client.create_slash_command(commands.Play)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config)
    client.register_interaction_handler("play", lambda event: http_client.respond_interaction_with_message(event, "OK!"))
    client.start()


def main2():
    config = Config()
    http_client = HttpClient(config)
    http_client.get_user_voice_channel(TEST_GUILD_ID, MY_USER_ID)


def main3():
    config = Config()
    http_client = HttpClient(config)
    # http_client.create_slash_command(commands.Play)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config)

    async def handle_play(event):
        http_client.respond_interaction_with_message(event, "Preparing join channel...")
        voice_session_data = await client.prepare_join_voice(TEST_GUILD_ID, TEST_CHANNEL_ID)
        voice_client = VoiceClient(TEST_GUILD_ID, voice_session_data["endpoint"], voice_session_data["session_id"], voice_session_data["token"], config)
        await voice_client.start()

    client.register_interaction_handler("play", handle_play)
    client.start()


main3()

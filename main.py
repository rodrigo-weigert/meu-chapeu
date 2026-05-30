#!/usr/bin/env python3

import asyncio
import commands
import http_client

from client import Client
from intents import Intent

voice_client = None
song_task = None


def main():
    http_client.create_slash_command(commands.Play)
    http_client.create_slash_command(commands.Skip)
    client = Client(Intent.GUILD_VOICE_STATES)

    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:  # Python <= 3.10
        pass


main()

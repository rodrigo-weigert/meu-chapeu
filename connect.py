#!/usr/bin/env python3

import requests
import asyncio
import websockets
import json
import random
from urllib.parse import urlencode

from client import Client
import event
from intents import Intent
from config import Config
from http_client import HttpClient
import commands

def main():
    config = Config()
    http_client = HttpClient(config)
    http_client.create_slash_command(commands.Play)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config.api_token)
    client.register_interaction_handler("play", lambda event: http_client.respond_interaction_with_message(event, "OK!"))
    client.start()

main()

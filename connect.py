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

def main():
    config = Config()
    http_client = HttpClient(config)
    client = Client(http_client.get_gateway_url(), Intent.GUILD_VOICE_STATES, config.api_token)
    client.start()

main()

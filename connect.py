#!/usr/bin/env python3

import requests
import asyncio
import websockets
import json
import random
from urllib.parse import urlencode

import event

API_VERSION = "v10"
ENCODING = "json"
API_URL = f"https://discord.com/api/{API_VERSION}"

def req(path):
    return requests.get(f"{API_URL}{path}").json()

def get_gateway_url():
    base_url = req("/gateway")["url"]
    params = {"v": API_VERSION, "encoding": ENCODING}
    return f"{base_url}?/{urlencode(params)}"

async def loop_echo(wss_url):
    async with websockets.connect(wss_url) as websocket:
        hello = event.Event(await websocket.recv())
        print(f"Received: {hello}")
        heartbeat = hello.get("heartbeat_interval") / 1000
        jitter = random.random()
        print(f"Waiting {heartbeat * jitter} s...")
        await asyncio.sleep(heartbeat * jitter)
        await websocket.send(json.dumps({"d": None, "op": 1}))
        while True:
            resp = await websocket.recv()
            ack = event.Event(resp)
            print(f"Received: {ack}")
            await asyncio.sleep(heartbeat)
            await websocket.send(json.dumps({"d": None, "op": 1}))

gateway_url = get_gateway_url()
print(f"Gateway URL: {gateway_url}")

try:
    asyncio.run(loop_echo(gateway_url))
except KeyboardInterrupt:
    print("Closing...")

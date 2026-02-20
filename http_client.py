#!/usr/bin/env python3

import httpx
import json
from urllib.parse import urlencode

from config import Config
from event import Event
from typing import Dict, Any
from logs import logger as base_logger
from interactions import InteractionType, InteractionFlag

logger = base_logger.bind(context="HttpClient")


class HttpClient:
    _config: Config
    _api_url: str
    _aclient: httpx.AsyncClient
    _client: httpx.Client

    def __init__(self, config: Config):
        headers = {"Authorization": f"Bot {config.api_token}"}
        self._config = config
        self._api_url = f"{config.api_url}/{config.api_version}"
        self._aclient = httpx.AsyncClient(headers=headers)
        self._client = httpx.Client(headers=headers)

    def get_gateway_url(self) -> str:
        base_url = self._get("/gateway")["url"]
        params = {"v": self._config.api_version, "encoding": self._config.encoding}
        return f"{base_url}?/{urlencode(params)}"

    def create_slash_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        logger.log("OUT", f"Creating command {json.dumps(params)}")
        resp = self._post(f"/applications/{self._config.application_id}/commands", body=params).json()
        logger.log("IN", f"Command creation response: {resp}")
        return resp

    async def get_user_voice_channel(self, guild_id: str, user_id: str) -> str | None:
        resp = await self._aget(f"/guilds/{guild_id}/voice-states/{user_id}")
        return resp.get("channel_id")

    async def respond_interaction_with_message(self, interaction_event: Event, message: str, ephemeral=False, deferred=False) -> bool:
        id = interaction_event["id"]
        token = interaction_event["token"]
        respond_url = f"/interactions/{id}/{token}/callback"
        flags = InteractionFlag.SUPRESS_EMBEDS

        logger.log("OUT", f"RESPONDING INTERACTION {id}")

        if ephemeral:
            flags |= InteractionFlag.EPHEMERAL
        interaction_type = InteractionType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE if deferred else InteractionType.CHANNEL_MESSAGE_WITH_SOURCE

        resp = await self._apost(respond_url, {"type": interaction_type, "data": {"content": message, "flags": flags}})

        success = resp.status_code >= 200 and resp.status_code < 300
        if success:
            logger.log("IN", f"INTERACTION {id} RESPONSE SUCCESSFUL, STATUS {resp.status_code}")
        else:
            logger.warning(f"INTERACTION {id} RESPONSE ERROR, STATUS {resp.status_code}, BODY: {resp.json()}")

        return success

    async def update_original_interaction_response(self, interaction_event: Event, message: str) -> bool:
        id = interaction_event["id"]
        token = interaction_event["token"]
        respond_url = f"/webhooks/{self._config.application_id}/{token}/messages/@original"

        logger.log("OUT", f"UPDATING INTERACTION {id}")
        resp = await self._apatch(respond_url, {"content": message, "flags": InteractionFlag.SUPRESS_EMBEDS})
        logger.log("IN", f"INTERACTION {id} UPDATE RESPONSE GOT STATUS {resp.status_code}")
        return resp.status_code >= 200 and resp.status_code < 300

    def _get(self, path: str) -> Dict[str, Any]:
        return self._client.get(f"{self._api_url}{path}").json()

    def _post(self, path: str, body: Dict[str, Any]) -> httpx.Response:
        return self._client.post(f"{self._api_url}{path}", json=body)

    async def _aget(self, path: str) -> Dict[str, Any]:
        return (await self._aclient.get(f"{self._api_url}{path}")).json()

    async def _apost(self, path: str, body: Dict[str, Any]) -> httpx.Response:
        return await self._aclient.post(f"{self._api_url}{path}", json=body)

    async def _apatch(self, path: str, body: Dict[str, Any]) -> httpx.Response:
        return await self._aclient.patch(f"{self._api_url}{path}", json=body)

#!/usr/bin/env python3

import httpx
import json
from urllib.parse import urlencode

from config import config
from typing import Dict, Any
from logs import logger as base_logger
from interactions import InteractionType, InteractionFlag

logger = base_logger.bind(context="HttpClient")


_headers = {"Authorization": f"Bot {config.api_token}"}
_api_url = f"{config.api_url}/{config.api_version}"
_aclient = httpx.AsyncClient(headers=_headers)
_client = httpx.Client(headers=_headers)


def get_gateway_url() -> str:
    base_url = _get("/gateway")["url"]
    params = {"v": config.api_version, "encoding": config.encoding}
    return f"{base_url}?/{urlencode(params)}"


def create_slash_command(params: Dict[str, Any]) -> Dict[str, Any]:
    logger.log("OUT", f"Creating command {json.dumps(params)}")
    resp = _post(f"/applications/{config.application_id}/commands", body=params).json()
    logger.log("IN", f"Command creation response: {resp}")
    return resp


async def get_user_voice_channel(guild_id: str, user_id: str) -> str | None:
    resp = await _aget(f"/guilds/{guild_id}/voice-states/{user_id}")
    return resp.get("channel_id")


async def respond_interaction(id: str, token: str, message: str, ephemeral=False, deferred=False) -> bool:
    respond_url = f"/interactions/{id}/{token}/callback"
    flags = InteractionFlag.SUPRESS_EMBEDS

    logger.log("OUT", f"RESPONDING INTERACTION {id}")

    if ephemeral:
        flags |= InteractionFlag.EPHEMERAL
    interaction_type = InteractionType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE if deferred else InteractionType.CHANNEL_MESSAGE_WITH_SOURCE

    try:
        resp = await _apost(respond_url, {"type": interaction_type, "data": {"content": message, "flags": flags}})
    except httpx.TimeoutException as e:
        logger.warning(f"INTERACTION {id} RESPONSE TIMEOUT: {e}")
        return False

    success = resp.status_code >= 200 and resp.status_code < 300
    if success:
        logger.log("IN", f"INTERACTION {id} RESPONSE SUCCESSFUL, STATUS {resp.status_code}")
    else:
        logger.warning(f"INTERACTION {id} RESPONSE ERROR, STATUS {resp.status_code}, BODY: {resp.json()}")

    return success


def _get(path: str) -> Dict[str, Any]:
    return _client.get(f"{_api_url}{path}").json()


def _post(path: str, body: Dict[str, Any]) -> httpx.Response:
    return _client.post(f"{_api_url}{path}", json=body)


async def _aget(path: str) -> Dict[str, Any]:
    return (await _aclient.get(f"{_api_url}{path}")).json()


async def _apost(path: str, body: Dict[str, Any], timeout: float = 3.0) -> httpx.Response:
    return await _aclient.post(f"{_api_url}{path}", json=body, timeout=timeout)

#!/usr/bin/env python3

import requests
import json
from urllib.parse import urlencode

from config import Config
from event import Event
from typing import Dict, Any


class HttpClient:
    _api_url: str
    _config: Config

    def __init__(self, config: Config):
        self._config = config
        self._api_url = f"{config.api_url}/{config.api_version}"

    def _headers(self, auth: bool = False):
        if auth:
            return {"Authorization": f"Bot {self._config.api_token}"}
        return {}

    def get(self, path: str, auth: bool = False) -> Dict[str, Any]:
        headers = self._headers(auth)
        return requests.get(f"{self._api_url}{path}", headers=headers).json()

    def post(self, path: str, body: Dict[str, Any]) -> requests.Response:
        headers = self._headers(True)
        return requests.post(f"{self._api_url}{path}", headers=headers, json=body)

    def get_gateway_url(self) -> str:
        base_url = self.get("/gateway")["url"]
        params = {"v": self._config.api_version, "encoding": self._config.encoding}
        return f"{base_url}?/{urlencode(params)}"

    def create_slash_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"*** Creating command {json.dumps(params)}")
        resp = self.post(f"/applications/{self._config.application_id}/commands", body=params).json()
        print(f"*** Command created: {resp}")
        return resp

    def respond_interaction_with_message(self, interaction_event: Event, message: str) -> requests.Response:
        id = interaction_event.get("id")
        token = interaction_event.get("token")
        respond_url = f"/interactions/{id}/{token}/callback"
        print(f">>>>> RESPONDING INTERACTION {id}")
        resp = self.post(respond_url, {"type": 4, "data": {"content": message}})
        print(f"<<<<< STATUS {id}: {resp.status_code}")

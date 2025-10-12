#!/usr/bin/env python3

import requests
from urllib.parse import urlencode

from config import Config
from typing import Dict, Any

class HttpClient:
    _api_url: str
    _config: Config

    def __init__(self, config: Config):
        self._config = config
        self._api_url = f"{config.api_url}/{config.api_version}"

    def req(self, path) -> Dict[str, Any]:
        return requests.get(f"{self._api_url}{path}").json()

    def get_gateway_url(self) -> str:
        base_url = self.req("/gateway")["url"]
        params = {"v": self._config.api_version, "encoding": self._config.encoding}
        return f"{base_url}?/{urlencode(params)}"


import dotenv
import os

class Config:
    _api_token: str
    _api_version: str
    _encoding: str
    _api_url: str

    def __init__(self, env_file: str = ".env"):
        dotenv.load_dotenv(env_file)
        self._api_token = os.getenv("API_TOKEN")
        self._api_version = os.getenv("API_VERSION")
        self._encoding = os.getenv("API_ENCODING")
        self._api_url = os.getenv("API_URL")

    @property
    def api_token(self):
        return self._api_token

    @property
    def api_version(self):
        return self._api_version

    @property
    def encoding(self):
        return self._encoding
    
    @property
    def api_url(self):
        return self._api_url

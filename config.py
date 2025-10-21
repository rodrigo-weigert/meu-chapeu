import dotenv
import os


class Config:
    _api_token: str | None
    _api_version: str | None
    _encoding: str | None
    _api_url: str | None
    _application_id: str | None
    _idle_timeout: int | None

    def __init__(self, env_file: str = ".env"):
        dotenv.load_dotenv(env_file)
        self._api_token = os.getenv("API_TOKEN")
        self._api_version = os.getenv("API_VERSION")
        self._encoding = os.getenv("API_ENCODING")
        self._api_url = os.getenv("API_URL")
        self._application_id = os.getenv("APPLICATION_ID")
        self._idle_timeout = int(os.getenv("IDLE_TIMEOUT", default=300))

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

    @property
    def application_id(self):
        return self._application_id

    @property
    def idle_timeout(self):
        return self._idle_timeout

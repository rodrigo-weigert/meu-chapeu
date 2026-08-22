from arguments import args
import dotenv
import os

__all__ = ["config", "MissingConfigError"]


class MissingConfigError(Exception):
    pass


def _get_or_raise(env_var: str) -> str:
    value = os.getenv(env_var)
    if value is None:
        raise MissingConfigError(f"Environment variable {env_var} must be set")
    return value


class Config:
    _application_id: str
    _api_token: str
    _api_version: str
    _api_url: str
    _idle_timeout: int
    _google_api_token: str

    def __init__(self, env_file: str = ".env"):
        dotenv.load_dotenv(env_file)
        self._application_id = _get_or_raise("APPLICATION_ID")
        self._api_token = _get_or_raise("API_TOKEN")
        self._api_version = os.getenv("API_VERSION", default="v10")
        self._api_url = os.getenv("API_URL", default="https://discord.com/api")
        self._idle_timeout = int(os.getenv("IDLE_TIMEOUT", default=600))
        self._google_api_token = _get_or_raise("GOOGLE_API_TOKEN")

    @property
    def api_token(self) -> str:
        return self._api_token

    @property
    def api_version(self) -> str:
        return self._api_version

    @property
    def api_url(self) -> str:
        return self._api_url

    @property
    def application_id(self) -> str:
        return self._application_id

    @property
    def idle_timeout(self) -> int:
        return self._idle_timeout

    @property
    def google_api_token(self) -> str:
        return self._google_api_token


config = Config(env_file=args.env)

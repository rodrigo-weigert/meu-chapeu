import httpx
import tempfile
import urllib.parse
import yt_dlp
import isodate  # type: ignore[import-untyped]

from logs import logger as base_logger
from config import config
from media_file import MediaFile
from pathlib import Path
from arguments import args

__all__ = ["fetch_media_for_query"]

_API_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_API_INFO_URL = "https://www.googleapis.com/youtube/v3/videos"

_logger = base_logger.bind(context="YoutubeDL")
_SAVE_DIR = Path(tempfile.gettempdir()) / 'meu-chapeu'

_client = httpx.AsyncClient()


class _YoutubeDLLogger:
    def debug(self, msg):
        if args.ydl_verbose:
            _logger.info(msg)

    def warning(self, msg):
        _logger.warning(msg)

    def error(self, msg):
        _logger.error(msg)


_YDL_OPTS = {
    'format': 'bestaudio/bestaudio*[height<=480]',
    'logger': _YoutubeDLLogger(),
    'outtmpl': str(_SAVE_DIR / "%(id)s"),
    'allowed_extractors': ["youtube"],
    'verbose': args.ydl_verbose,
    'extractor_args': {'youtube': {'skip': ['hls', 'translated_subs']}},
    'noplaylist': True
}

_ydl = yt_dlp.YoutubeDL(params=_YDL_OPTS)  # type: ignore[arg-type]


async def _video_id_from_search(query: str) -> str | None:
    params = {"part": "snippet",
              "type": "video",
              "key": config.google_api_token,
              "q": query,
              "regionCode": "BR",
              "relevanceLanguage": "pt"}
    headers = {"Accept": "application/json"}
    _logger.info(f"Searching YouTube for query '{query}'")
    res = await _client.get(_API_SEARCH_URL, headers=headers, params=params)
    if res.status_code == 200:
        results = res.json()["items"]
        if len(results) > 0:
            video_id = results[0]["id"]["videoId"]
            _logger.info(f"Found video ID {video_id} for query '{query}'")
            return video_id
        _logger.info(f"Search for '{query}' returned no results")
        return None
    else:
        _logger.warning(f"YouTube API returned {res.status_code}")
        return None


def _file_path(video_id: str) -> Path:
    return _SAVE_DIR / video_id


def _youtube_link(video_id: str) -> str:
    return f"https://youtube.com/watch?v={video_id}"


def _download(video_id: str) -> bool:
    path = _file_path(video_id)
    if path.is_file():
        _logger.info(f"Video ID {video_id} is already downloaded, skipping download")
        return True

    _logger.info(f"Downloading video ID {video_id}")
    try:
        _ydl.download([_youtube_link(video_id)])
    except yt_dlp.utils.DownloadError:
        _logger.error(f"Failed to download video ID {video_id}")
        return False
    _logger.info(f"Downloaded video ID {video_id} successfully")
    return True


def _video_id_from_url(user_query: str) -> str | None:
    parsed_url = urllib.parse.urlparse(user_query)
    parsed_qs = urllib.parse.parse_qs(parsed_url.query)
    video_id = ""

    if "v" in parsed_qs:
        video_id = parsed_qs["v"][0]
    elif parsed_url.netloc.lower() == "youtu.be":
        video_id = parsed_url.path[1:]

    return video_id if len(video_id) == 11 else None


async def _get_video_id(user_query: str) -> str | None:
    video_id = _video_id_from_url(user_query)
    if video_id is not None:
        _logger.info(f"Extracted video ID {video_id} from user query '{user_query}'")
        return video_id
    return await _video_id_from_search(user_query)


async def _build_media_file(video_id: str) -> MediaFile | None:
    params = {"part": ["snippet", "contentDetails", "statistics"],
              "key": config.google_api_token,
              "id": video_id}
    headers = {"Accept": "application/json"}
    _logger.info(f"Fetching metadata for video ID {video_id}")
    res = await _client.get(_API_INFO_URL, headers=headers, params=params)
    if res.status_code == 200:
        data = res.json()["items"][0]
        return MediaFile(id=video_id,
                         file_path=_file_path(video_id),
                         link=_youtube_link(video_id),
                         title=data["snippet"]["title"],
                         thumbnail=data["snippet"]["thumbnails"]["default"]["url"],
                         duration=int(isodate.parse_duration(data["contentDetails"]["duration"]).total_seconds()),
                         views=int(data["statistics"]["viewCount"]),
                         likes=int(data["statistics"]["likeCount"]),
                         published_at=isodate.parse_datetime(data["snippet"]["publishedAt"]),
                         download_fn=lambda: _download(video_id))
    return None


async def fetch_media_for_query(user_query: str) -> MediaFile | None:
    video_id = await _get_video_id(user_query)
    if video_id is None:
        _logger.warning(f"Failed to find video for query '{user_query}'")
        return None

    media_file = await _build_media_file(video_id)
    if media_file is None:
        _logger.error(f"Failed to retrieve data about video ID {video_id} for query '{user_query}'")
        return None

    return media_file

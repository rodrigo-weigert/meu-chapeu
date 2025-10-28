import os
import requests
import tempfile
import urllib.parse
import yt_dlp
import isodate

from logs import logger as base_logger
from config import Config
from media_file import MediaFile

API_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
API_INFO_URL = "https://www.googleapis.com/youtube/v3/videos"

logger = base_logger.bind(context="YoutubeDL")
SAVE_DIR = os.path.join(tempfile.gettempdir(), 'meu-chapeu')


class YoutubeDLLogger:
    def debug(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


YDL_OPTS = {'format': 'm4a/bestaudio/bestaudio*[height<=480]',
            'logger': YoutubeDLLogger(),
            'outtmpl': os.path.join(SAVE_DIR, "%(id)s"),
            'allowed_extractors': ["youtube"],
            'verbose': True}

ydl = yt_dlp.YoutubeDL(params=YDL_OPTS)  # type: ignore[arg-type]


def video_id_from_search(query: str, config: Config) -> str | None:
    params = {"part": "snippet",
              "type": "video",
              "key": config.google_api_token,
              "q": query,
              "regionCode": "BR",
              "relevanceLanguage": "pt"}
    headers = {"Accept": "application/json"}
    logger.info(f"Searching YouTube for query '{query}'")
    res = requests.get(API_SEARCH_URL, headers=headers, params=params)
    if res.status_code == 200:
        video_id = res.json()["items"][0]["id"]["videoId"]
        logger.info(f"Found video ID {video_id} for query '{query}'")
        return video_id
    else:
        logger.warning(f"YouTube API returned {res.status_code}")
        return None


def file_path(video_id: str) -> str:
    return os.path.join(SAVE_DIR, video_id)


def youtube_link(video_id: str) -> str:
    return f"https://youtube.com/watch?v={video_id}"


def download(video_id: str) -> bool:
    logger.info(f"Downloading video ID {video_id}")
    try:
        ydl.download([youtube_link(video_id)])
    except yt_dlp.utils.DownloadError:
        logger.error(f"Failed to download video ID {video_id}")
        return False
    logger.info(f"Downloaded video ID {video_id} successfully")
    return True


def video_id_from_url(user_query: str) -> str | None:
    parsed_url = urllib.parse.urlparse(user_query)
    parsed_qs = urllib.parse.parse_qs(parsed_url.query)
    video_id = ""

    if "v" in parsed_qs:
        video_id = parsed_qs["v"][0]
    elif parsed_url.netloc.lower() == "youtu.be":
        video_id = parsed_url.path[1:]

    return video_id if len(video_id) == 11 else None


def get_video_id(user_query: str, config: Config) -> str | None:
    video_id = video_id_from_url(user_query)
    if video_id is not None:
        logger.info(f"Extracted video ID {video_id} from user query '{user_query}'")
        return video_id
    return video_id_from_search(user_query, config)


def build_media_file(video_id: str, config: Config) -> MediaFile | None:
    params = {"part": ["snippet", "contentDetails"],
              "key": config.google_api_token,
              "id": video_id}
    headers = {"Accept": "application/json"}
    logger.info(f"Fetching metadata for video ID {video_id}")
    res = requests.get(API_INFO_URL, headers=headers, params=params)
    if res.status_code == 200:
        json = res.json()
        return MediaFile(id=video_id,
                         file_path=file_path(video_id),
                         link=youtube_link(video_id),
                         title=json["items"][0]["snippet"]["title"],
                         thumbnail=json["items"][0]["snippet"]["thumbnails"]["default"]["url"],
                         duration=int(isodate.parse_duration(json["items"][0]["contentDetails"]["duration"]).total_seconds()),
                         download_fn=lambda: download(video_id))
    return None


def get_video_from_user_query(user_query: str, config: Config) -> MediaFile | None:
    video_id = get_video_id(user_query, config)
    if video_id is None:
        logger.warning(f"Failed to find video for query '{user_query}'")
        return None

    logger.info(f"Found video ID {video_id} for query '{user_query}'")

    media_file = build_media_file(video_id, config)
    if media_file is None:
        logger.error(f"Failed to retrieve data about video ID {video_id} for query '{user_query}'")
        return None

    return build_media_file(video_id, config)

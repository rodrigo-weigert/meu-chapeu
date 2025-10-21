import os
import requests
import tempfile
import urllib.parse
import youtube_dl

from logs import logger as base_logger
from config import Config

API_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

logger = base_logger.bind(context="YoutubeDL")
SAVE_DIR = os.path.join(tempfile.gettempdir(), 'meu-chapeu')


class YoutubeDLLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def video_id_from_search(query: str, config: Config) -> str | None:
    params = {"part": "snippet",
              "type": "video",
              "key": config.google_api_token,
              "q": query,
              "regionCode": "BR",
              "relevanceLanguage": "pt"}
    headers = {"Accept": "application/json"}
    logger.info(f"Searching YouTube for query {query}")
    res = requests.get(API_SEARCH_URL, headers=headers, params=params)
    if res.status_code == 200:
        video_id = res.json()["items"][0]["id"]["videoId"]
        logger.info(f"Found video ID {video_id} for query '{query}'")
        return video_id
    else:
        logger.warning(f"YouTube API returned {res.status_code}")
        return None


YDL_OPTS = {'format': 'bestaudio/best', 'logger': YoutubeDLLogger(), 'outtmpl': os.path.join(SAVE_DIR, "%(id)s")}


def maybe_download(video_id: str) -> str | None:
    file_path = os.path.join(SAVE_DIR, video_id)

    if os.path.isfile(file_path):
        return file_path

    with youtube_dl.YoutubeDL(YDL_OPTS) as ydl:
        result = ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
        if result == 0:
            return file_path
        return None


def video_id_from_url(user_query: str) -> str | None:
    parsed_url = urllib.parse.urlparse(user_query)
    parsed_qs = urllib.parse.parse_qs(parsed_url.query)
    video_id = ""

    match parsed_url.netloc.lower():
        case "youtube.com" | "www.youtube.com":
            if "v" in parsed_qs:
                video_id = parsed_qs["v"][0]
        case "youtu.be":
            video_id = parsed_url.path[1:]
        case _:
            pass

    return video_id if len(video_id) == 11 else None


def get_video_id(user_query: str, config: Config) -> str | None:
    video_id = video_id_from_url(user_query)
    if video_id is not None:
        logger.info(f"Extracted video ID {video_id} from user query '{user_query}'")
        return video_id
    return video_id_from_search(user_query, config)


def get_video(user_query: str, config: Config) -> str | None:
    video_id = get_video_id(user_query, config)
    if video_id is None:
        logger.warning(f"Failed to find video for query '{user_query}'")
        return None

    logger.info(f"Fetching video ID {video_id}")

    file_path = maybe_download(video_id)
    if file_path is None:
        logger.warning(f"Failed to download video ID {video_id} for query '{user_query}'")
        return None

    logger.info(f"Video ID {video_id} for query '{user_query}' is saved at {file_path}")
    return file_path

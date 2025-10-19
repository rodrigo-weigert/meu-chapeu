import os
import requests
import tempfile
import youtube_dl
from logs import logger as base_logger

API_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
TOKEN = "REDACTED"  # TODO put in config/dotenv

logger = base_logger.bind(context="YoutubeDL")
SAVE_DIR = os.path.join(tempfile.gettempdir(), 'meu-chapeu')


class YoutubeDLLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def search(query: str) -> str | None:
    params = {"part": "snippet",
              "type": "video",
              "key": TOKEN,
              "q": query,
              "regionCode": "BR",
              "relevanceLanguage": "pt"}
    headers = {"Accept": "application/json"}
    res = requests.get(API_SEARCH_URL, headers=headers, params=params)
    if res.status_code == 200:
        return res.json()["items"][0]["id"]["videoId"]
    else:
        logger.warning(f"YouTube API returned {res.status_code}")
        return None


YDL_OPTS = {'format': 'bestaudio/best', 'logger': YoutubeDLLogger(), 'outtmpl': os.path.join(SAVE_DIR, "%(id)s")}


def download(video_id: str) -> str | None:
    with youtube_dl.YoutubeDL(YDL_OPTS) as ydl:
        result = ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
        if result == 0:
            return os.path.join(SAVE_DIR, video_id)
        return None


def search_and_download_first(query: str) -> str | None:
    logger.info(f"Querying YouTube for '{query}'")
    video_id = search(query)
    if video_id is None:
        logger.warning(f"Video search for query '{query}' failed")
        return None

    logger.info(f"Downloading video ID {video_id}")

    file_path = download(video_id)
    if file_path is None:
        logger.warning(f"Video ID {video_id} download for query '{query}' failed")
        return None
    logger.info(f"Successfully downloaded video ID {video_id} for query '{query}', saved at {file_path}")
    return file_path

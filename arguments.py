import argparse

_parser = argparse.ArgumentParser()
_parser.add_argument("-v", "--ydl-verbose", action="store_true", help="enables verbose yt-dlp logs")

args = _parser.parse_args()

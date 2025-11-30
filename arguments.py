import argparse

_parser = argparse.ArgumentParser()
_parser.add_argument("-v", "--ydl-verbose", action="store_true", help="enables verbose yt-dlp logs")
_parser.add_argument("-l", "--logfile", default="/tmp/meu-chapeu/meu-chapeu.log", help="specify log file path")

args = _parser.parse_args()

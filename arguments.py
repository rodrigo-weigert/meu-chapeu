import argparse

_parser = argparse.ArgumentParser()
_parser.add_argument("-v", "--ydl-verbose", action="store_true", help="enables verbose yt-dlp logs")
_parser.add_argument("-l", "--logfile", default="/tmp/meu-chapeu/meu-chapeu.log", help="specify log file path")
_parser.add_argument("--env", default=".env", help="use specified env file")
_parser.add_argument("--log-heartbeats", action="store_true", help="enables logging of outgoing heartbeats and incoming heartbeat acks")

args = _parser.parse_args()

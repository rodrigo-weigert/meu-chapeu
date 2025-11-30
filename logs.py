from arguments import args
import sys
from loguru import logger as base_logger
from pathlib import Path

LOGS_PATH = Path(args.logfile)


class Tee:
    def __init__(self, original_stream, file_path):
        self.original_stream = original_stream
        self.file = open(file_path, "a", buffering=1)

    def write(self, message):
        self.original_stream.write(message)
        self.file.write(message)

    def flush(self):
        self.original_stream.flush()
        self.file.flush()


LOGS_PATH.parent.mkdir(exist_ok=True)
sys.stderr = Tee(sys.stderr, LOGS_PATH)

base_logger.level("IN", no=20, color="<yellow>")
base_logger.level("OUT", no=20, color="<cyan>")

base_logger.remove()
base_logger.add(sys.stderr, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <level>{level}</level>: <b>[{extra[context]}]</b> {message}")

logger = base_logger.opt(colors=True).bind(context="DEFAULT")

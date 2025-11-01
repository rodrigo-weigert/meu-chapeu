import sys
from loguru import logger as base_logger

LOG_FILE_PATH = "/tmp/meu_chapeu.log"

base_logger.level("IN", no=20, color="<yellow>")
base_logger.level("OUT", no=20, color="<cyan>")

base_logger.remove()
# base_logger.add(sys.stderr, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <level>{level}</level>: <b>[{extra[context]}]</b> {message}")
base_logger.add(LOG_FILE_PATH, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <level>{level}</level>: <b>[{extra[context]}]</b> {message}")

logger = base_logger.opt(colors=True).bind(context="DEFAULT")

print(f"Logs are being written to {LOG_FILE_PATH}", file=sys.stderr)

import sys
from loguru import logger as base_logger

base_logger.remove()
base_logger.level("IN", no=20, color="<yellow>")
base_logger.level("OUT", no=20, color="<cyan>")
base_logger.add(sys.stderr, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <level>{level}</level>: [{extra[context]}] <b>{message}</b>")

logger = base_logger.opt(colors=True).bind(context="DEFAULT")

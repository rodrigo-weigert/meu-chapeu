import struct
import socket

from typing import Tuple
from logs import logger as base_logger

logger = base_logger.bind(context="UDP")

_IP_DISCOVERY_PACKET_FORMAT = "!HHI64sH"


def _ip_discovery_packet(ssrc: int) -> bytes:
    return struct.pack(_IP_DISCOVERY_PACKET_FORMAT, 0x1, 70, ssrc, b"", 0)


def _ip_discovery_response(resp: bytes) -> Tuple[str, int]:
    (_, _, _, ip, port) = struct.unpack(_IP_DISCOVERY_PACKET_FORMAT, resp)
    return (ip.decode().replace("\x00", ""), port)


def do_ip_discovery(sock: socket.socket, ssrc: int) -> Tuple[str, int]:
    logger.log("OUT", "IP DISCOVERY REQUEST")
    sock.send(_ip_discovery_packet(ssrc))
    (resp, from_addr) = sock.recvfrom(1024)
    parsed_resp = _ip_discovery_response(resp)
    logger.log("IN", f"IP DISCOVERY RESPONSE: {parsed_resp}")
    return parsed_resp

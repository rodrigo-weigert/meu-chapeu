import asyncio
import crypto
import struct
import socket
import random
import statistics

from typing import Tuple, List
from logs import logger as base_logger

logger = base_logger.bind(context="UDP")

_IP_DISCOVERY_PACKET_FORMAT = "!HHI64sH"
_RTP_HEADER_FORMAT = "!ccHII"


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


def _rtp_header(ssrc: int, seq: int, timestamp: int) -> bytes:
    return struct.pack(_RTP_HEADER_FORMAT, b'\x80', b'\x78', seq & ((1 << 16) - 1), timestamp & ((1 << 32) - 1), ssrc)


def _build_audio_packet(payload: bytes, ssrc: int, sequence: int, timestamp: int, encryption_key: bytes, nonce: int, encryption_mode: str) -> bytes:
    header = _rtp_header(ssrc, sequence, timestamp)
    encrypted_payload = crypto.encrypt_packet(header, payload, nonce, encryption_key, encryption_mode)
    return header + encrypted_payload + nonce.to_bytes(4, "little")


async def stream_audio(sock: socket.socket, audio_payloads: List[bytes], ssrc: int, initial_seq: int, encryption_key: List[int], nonce: int, encryption_mode: str) -> None:
    ts = random.getrandbits(32)  # TODO: should be voice client state
    k = bytes(encryption_key)
    loop = asyncio.get_event_loop()

    packets = (_build_audio_packet(payload, ssrc, initial_seq + i, ts + 960*i, k, nonce+i, encryption_mode) for (i, payload) in enumerate(audio_payloads))

    now = loop.time()
    next_time = now + 0.02

    for packet in packets:
        await asyncio.sleep(next_time - loop.time())
        sock.send(packet)
        next_time += 0.02

    logger.info(f"Audio stream end, duration: {0.02 * len(audio_payloads)} seconds, total packets: {len(audio_payloads)}")

import asyncio
import crypto
import random
import struct
import socket
import time

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


def stream_audio(sock: socket.socket, audio_payloads: List[bytes], ssrc: int, initial_seq: int, encryption_key: List[int], nonce: int, encryption_mode: str) -> None:
    logger.info("Starting audio stream")

    ts = random.getrandbits(32)  # TODO: should be voice client state
    k = bytes(encryption_key)

    packets = (_build_audio_packet(payload, ssrc, initial_seq + i, ts + 960*i, k, nonce+i, encryption_mode) for (i, payload) in enumerate(audio_payloads))

    now = time.perf_counter()
    next_time = now + 0.02

    try:
        for packet in packets:
            time.sleep(next_time - time.perf_counter())
            sock.send(packet)
            next_time += 0.02
    except OSError as e:
        if e.errno == 9:
            logger.info("Socket was closed. Stopping stream.")
        else:
            logger.warning(f"Socket was closed unexpectedly (error code = {e.errno}. Stopping stream.")
        return
    logger.info(f"Audio stream end, duration: {0.02 * len(audio_payloads)} seconds, total packets: {len(audio_payloads)}")

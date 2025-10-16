import asyncio
import crypto
import struct
import socket
import random
import time
import statistics

from typing import Tuple, List
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


_RTP_HEADER_FORMAT = "!ccHII"


def _rtp_header(ssrc: int, seq: int, timestamp: int) -> bytes:
    return struct.pack(_RTP_HEADER_FORMAT, b'\x80', b'\x78', seq & ((1 << 16) - 1), timestamp & ((1 << 32) - 1), ssrc)


def _build_audio_packet(payload: bytes, ssrc: int, sequence: int, timestamp: int, encryption_key: bytes, nonce: int) -> bytes:
    header = _rtp_header(ssrc, sequence, timestamp)
    encrypted_payload = crypto.encrypt_packet(header, payload, nonce, encryption_key)
    return header + encrypted_payload + nonce.to_bytes(4, "little")

# TODO investigate and fix stream skipping / hiccup issue
async def stream_audio(sock: socket.socket, audio_payloads: List[bytes], ssrc: int, initial_seq: int, encryption_key: List[int], nonce: int) -> None:
    ts = random.getrandbits(32)
    k = bytes(encryption_key)

    packets = [_build_audio_packet(payload, ssrc, initial_seq + i, ts + 960*i, k, nonce+i) for (i, payload) in enumerate(audio_payloads)]
    next_time = time.perf_counter()
    last = next_time
    diffs = []
    logger.info(f"Max packet size: {max([len(packet) for packet in packets])}")
    for packet in packets:
        next_time += 0.02
        now = time.perf_counter()
        sleep_time = next_time - now
        if sleep_time > 0:
            await asyncio.sleep(sleep_time * 0.9)
            while time.perf_counter() < next_time:
                pass
        else:
            logger.warning("Accumulated drift, packets are late!")
        sock.send(packet)
        now = time.perf_counter()
        diff = now - last
        last = now
        diffs.append(diff)

    quantiles = statistics.quantiles(diffs, n=100)
    logger.info(f"Audio stream end, avg packet interval {statistics.mean(diffs)}, max: {max(diffs)}, min: {min(diffs)}, p1: {quantiles[0]}, p99: {quantiles[98]}")

import crypto
import random
import struct
import socket
import time
import threading

from typing import Tuple, List
from logs import logger as base_logger
from dave.session import DaveSessionManager, MediaKey

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


# TODO double check if this is correct
def _to_uleb128(val: int) -> bytes:
    result = b''
    while val >= 0x80:
        result += (0x80 | (val & 0x7F)).to_bytes()
        val >>= 7
    result += val.to_bytes()
    return result


def _build_dave_payload(payload: bytes, media_key: MediaKey) -> bytes:
    ciphertext, tag = crypto.encrypt_dave(payload, media_key.nonce, media_key.key)
    sync_nonce = _to_uleb128(int.from_bytes(media_key.nonce, "big"))
    supplemental_data_size = len(tag) + len(sync_nonce) + 3
    return ciphertext + tag + sync_nonce + supplemental_data_size.to_bytes() + b'\xFA\xFA'


def _build_audio_packet(payload: bytes, ssrc: int, sequence: int, timestamp: int,
                        encryption_key: bytes, nonce: int, encryption_mode: str,
                        dave: DaveSessionManager) -> bytes:
    header = _rtp_header(ssrc, sequence, timestamp)

    try:
        media_key = dave.get_current_media_key(nonce >> 24)
        if media_key is not None:
            payload = _build_dave_payload(payload, media_key)
    except Exception as e:
        logger.error(f"Exception building DAVE packet: {e}")

    trunc_nonce = nonce & 0xFFFFFFFF
    encrypted_payload = crypto.encrypt_packet(header, payload, trunc_nonce, encryption_key, encryption_mode)
    return header + encrypted_payload + trunc_nonce.to_bytes(4, "little")


def stream_audio(sock: socket.socket, audio_payloads: List[bytes], ssrc: int,
                 initial_seq: int, encryption_key: List[int], nonce: int,
                 encryption_mode: str, stop_event: threading.Event, dave: DaveSessionManager) -> int:
    logger.info("Starting audio stream")

    ts = random.getrandbits(32)  # TODO: should be voice client state
    k = bytes(encryption_key)

    packets = (_build_audio_packet(payload, ssrc, initial_seq + i, ts + 960*i, k, nonce+i, encryption_mode, dave) for (i, payload) in enumerate(audio_payloads))

    now = time.perf_counter()
    next_time = now + 0.02
    sent_packets = 0

    try:
        for packet in packets:
            if stop_event.is_set():
                logger.info("Received stop event, stopping stream")
                break
            sleep_amount = next_time - time.perf_counter()
            if sleep_amount > 0:
                time.sleep(sleep_amount)
            sock.send(packet)
            sent_packets += 1
            next_time += 0.02
    except OSError as e:
        if e.errno == 9:
            logger.info("Socket was closed. Stopping stream.")
        else:
            logger.warning(f"Socket was closed unexpectedly (error code = {e.errno}. Stopping stream.")
    logger.info(f"Audio stream end, duration: {0.02 * sent_packets} seconds, total packets sent: {sent_packets}")
    return sent_packets

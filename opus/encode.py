import ctypes
import os
import subprocess
import tempfile
import time
import uuid

from typing import List
from logs import logger as base_logger

logger = base_logger.bind(context="OpusEncoder")

SILENCE_FRAME = b'\xf8\xff\xfe'

_root_path = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.cdll.LoadLibrary(os.path.join(_root_path, "opus_encode.so"))

_lib.get_opus_packets.argtypes = [ctypes.POINTER(ctypes.c_char),                    # char* pcm_filename
                                  ctypes.POINTER(ctypes.c_size_t),                  # size_t* packet_count
                                  ctypes.POINTER(ctypes.POINTER(ctypes.c_size_t))]  # size_t** packet_length
_lib.get_opus_packets.restype = ctypes.POINTER(ctypes.c_ubyte)

_lib.free_buffer.argtypes = [ctypes.c_void_p]
_lib.free_buffer.restype = None


def _pcm_file_to_opus_packets(pcm_filename: str) -> List[bytes]:
    start_time = time.perf_counter()
    c_packet_count = ctypes.c_size_t()
    c_packet_lengths = ctypes.POINTER(ctypes.c_size_t)()
    out_ptr = _lib.get_opus_packets(bytes(pcm_filename, encoding="ascii"), ctypes.byref(c_packet_count), ctypes.byref(c_packet_lengths))
    packet_count = c_packet_count.value
    c_lib_time = time.perf_counter() - start_time
    logger.info(f"C Opus encoding finished in {c_lib_time:.2f} s.")

    offsets = [0] * packet_count
    for i in range(1, packet_count):
        offsets[i] = offsets[i-1] + c_packet_lengths[i-1]

    offset_time = time.perf_counter() - start_time - c_lib_time
    logger.info(f"Offset computation finished in {offset_time:.2f} s.")

    output = [bytes(out_ptr[offsets[i]:offsets[i]+c_packet_lengths[i]]) for i in range(packet_count)]
    bytes_time = time.perf_counter() - start_time - c_lib_time - offset_time
    logger.info(f"Bytes objects creation finished in {bytes_time:.2f} s.")

    _lib.free_buffer(c_packet_lengths)
    _lib.free_buffer(out_ptr)
    return output


def _media_file_to_pcm(media_filename: str) -> str:
    pcm_filename = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    ffmpeg_cmd = ["ffmpeg", "-hide_banner",
                  "-i", media_filename,
                  "-f", "s16le",
                  "-ar", "48000",
                  "-ac", "2",
                  "-vn",
                  "-loglevel", "error",
                  pcm_filename]
    proc = subprocess.Popen(ffmpeg_cmd, bufsize=0)
    exit_code = proc.wait()
    if exit_code != 0:
        raise Exception(f"Failed to convert media file to PCM, FFmpeg exit code {exit_code}")
    return pcm_filename


def encode(media_filename: str) -> List[bytes]:
    logger.info(f"Starting FFmpeg conversion of media file {media_filename} to PCM...")

    start_time = time.perf_counter()
    pcm_filename = _media_file_to_pcm(media_filename)
    pcm_duration = time.perf_counter() - start_time
    logger.info(f"PCM conversion of {media_filename} finished in {pcm_duration:.2f} s. Encoding using Opus Codec...")
    result = _pcm_file_to_opus_packets(pcm_filename)
    opus_duration = time.perf_counter() - start_time - pcm_duration
    logger.info(f"Opus encoding of {media_filename} finished in {opus_duration:.2f} s.")
    os.remove(pcm_filename)
    result.extend(5 * [SILENCE_FRAME])
    return result

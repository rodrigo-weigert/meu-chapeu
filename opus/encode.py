import ctypes
import os
import subprocess
import tempfile
import uuid

from typing import List
from logs import logger as base_logger

logger = base_logger.bind(context="OpusEncoder")

SILENCE_FRAME = b'\xf8\xff\xfe'

_root_path = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.cdll.LoadLibrary(os.path.join(_root_path, "opus_encode.so"))

_lib.get_opus_packets.argtypes = [ctypes.POINTER(ctypes.c_char),                 # char* pcm_filename
                                  ctypes.POINTER(ctypes.c_int),                  # int* packet_count
                                  ctypes.POINTER(ctypes.POINTER(ctypes.c_int))]  # int** packet_length
_lib.get_opus_packets.restype = ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))

_lib.free_buffer.argtypes = [ctypes.c_void_p]
_lib.free_buffer.restype = None


def _pcm_file_to_opus_packets(pcm_filename: str) -> List[bytes]:
    c_packet_count = ctypes.c_int()
    c_packet_lengths = ctypes.POINTER(ctypes.c_int)()
    out_ptr = _lib.get_opus_packets(bytes(pcm_filename, encoding="ascii"), ctypes.byref(c_packet_count), ctypes.byref(c_packet_lengths))
    packet_count = c_packet_count.value
    packet_lengths = [c_packet_lengths[i] for i in range(packet_count)]
    output = [bytes(out_ptr[i][:packet_lengths[i]]) for i in range(packet_count)]
    _lib.free_buffer(c_packet_lengths)
    for i in range(packet_count):
        _lib.free_buffer(out_ptr[i])
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
    pcm_filename = _media_file_to_pcm(media_filename)
    logger.info(f"PCM conversion of {media_filename} finished. Encoding using Opus Codec...")
    result = _pcm_file_to_opus_packets(pcm_filename)
    logger.info(f"Opus encoding of {media_filename} finished")
    os.remove(pcm_filename)
    result.extend(5 * [SILENCE_FRAME])
    return result

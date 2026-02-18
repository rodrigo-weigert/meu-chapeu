import ctypes
import os
import subprocess
import threading

from typing import Iterator
from logs import logger as base_logger

logger = base_logger.bind(context="OpusEncoder")

_SILENCE_FRAME = b'\xf8\xff\xfe'

_SAMPLING_RATE = 48000
_CHANNELS = 2
_PACKET_DURATION_MS = 20
_SAMPLE_BYTE_SIZE = 2
_CHUNK_SIZE = _SAMPLING_RATE * _PACKET_DURATION_MS * _CHANNELS * _SAMPLE_BYTE_SIZE // 1000
_FFMPEG_BUFFER_CHUNKS = 500

# ctypes

_root_path = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.cdll.LoadLibrary(os.path.join(_root_path, "opus_encode.so"))

# free_buffer
_lib.free_buffer.argtypes = [ctypes.c_void_p]
_lib.free_buffer.restype = None

# create_encoder
_lib.create_encoder.argtypes = []
_lib.create_encoder.restype = ctypes.c_void_p

# destroy_encoder
_lib.destroy_encoder.argtypes = [ctypes.c_void_p]
_lib.destroy_encoder.restype = None

# encode
_lib.encode.argtypes = [
    ctypes.c_void_p,                 # OpusEncoder* encoder
    ctypes.c_void_p,                 # opus_int16* pcm
    ctypes.POINTER(ctypes.c_size_t)  # size_t* out_len
]
_lib.encode.restype = ctypes.POINTER(ctypes.c_ubyte)


class OpusEncodingException(Exception):
    pass


class _PCMEncoder:
    _filename: str

    def __init__(self, filename: str) -> None:
        self._filename = filename

    def pcm_stream(self) -> Iterator[bytes]:
        proc = subprocess.Popen(
            self._ffmpeg_cmd(),
            bufsize=_FFMPEG_BUFFER_CHUNKS * _CHUNK_SIZE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        assert proc.stdout is not None
        process_finished = False
        logger.info(f"Starting FFmpeg PCM stream of {self._filename}")
        try:
            while True:
                packet = proc.stdout.read(_CHUNK_SIZE)
                if not packet:
                    break
                yield packet
            process_finished = True
        finally:
            if process_finished:
                exit_code = proc.wait()
                if exit_code != 0:
                    logger.error(f"FFmpeg terminated with error (exit code {exit_code})")
                    raise OpusEncodingException(f"FFmpeg terminated with exit code {exit_code}")
                else:
                    logger.info("FFmpeg stream finished")
            else:
                logger.info("Terminating FFmpeg stream (early interruption)...")
                proc.terminate()
                proc.stdout.close()
                try:
                    proc.wait(timeout=5)
                    logger.info("FFmpeg stream terminated")
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg termination timeout expired, killing process...")
                    proc.kill()
                    proc.wait()
                    logger.info("FFmpeg process killed")

    def _ffmpeg_cmd(self) -> list[str]:
        return ["ffmpeg",
                "-hide_banner",
                "-i", self._filename,
                "-f", "s16le",
                "-ar", str(_SAMPLING_RATE),
                "-ac", str(_CHANNELS),
                "-vn",
                "-loglevel", "error",
                "-"]


class _OpusEncoder:
    _encoder: ctypes.c_void_p

    def __init__(self) -> None:
        self._encoder = _lib.create_encoder()

    def encode(self, data: bytes) -> bytes:
        padding = _CHUNK_SIZE - len(data)
        padded_data = data + b'\x00' * padding
        buf = (ctypes.c_ubyte * len(padded_data)).from_buffer_copy(padded_data)
        out_len = ctypes.c_size_t()
        out_ptr = _lib.encode(self._encoder, buf, ctypes.byref(out_len))
        if out_ptr:
            ret = bytes(out_ptr[:out_len.value])
            _lib.free_buffer(out_ptr)
            return ret
        logger.error("Failed to encode packet")
        raise OpusEncodingException("Failed to encode packet")

    def __del__(self) -> None:
        _lib.destroy_encoder(self._encoder)


def encode(media_filename: str) -> Iterator[bytes]:
    pcm_enc = _PCMEncoder(media_filename)
    opus_enc = _OpusEncoder()
    opus_stream = (opus_enc.encode(pcm_chunk) for pcm_chunk in pcm_enc.pcm_stream())
    yield from opus_stream
    yield from [_SILENCE_FRAME] * 5

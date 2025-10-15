import ctypes
import os

from typing import List

_root_path = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.cdll.LoadLibrary(os.path.join(_root_path, "opus_encode.so"))

_lib.get_opus_packets.argtypes = [ctypes.POINTER(ctypes.c_char),                 # char* pcm_filename
                                  ctypes.POINTER(ctypes.c_int),                  # int* packet_count
                                  ctypes.POINTER(ctypes.POINTER(ctypes.c_int))]  # int** packet_length
_lib.get_opus_packets.restype = ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))

_lib.free_buffer.argtypes = [ctypes.c_void_p]
_lib.free_buffer.restype = None


def get_opus_packets(pcm_filename: str) -> List[bytes]:
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

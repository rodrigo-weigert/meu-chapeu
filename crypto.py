from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


from dave.parser import KDFLabel

from typing import Tuple


def encrypt_packet(header: bytes, payload: bytes, nonce: int, key: bytes, mode: str) -> bytes:
    match mode:
        case "aead_xchacha20_poly1305_rtpsize":
            return crypto_aead_xchacha20poly1305_ietf_encrypt(payload, header, nonce.to_bytes(24, "little"), key)

        case "aead_aes256_gcm_rtpsize":
            return AESGCM(key).encrypt(nonce.to_bytes(12, "little"), payload, header)

        case _:
            raise NotImplementedError(f"Unimplemented transport encryption mode: {mode}")


# TODO better names
def encrypt_dave(payload: bytes, nonce: int, key: bytes) -> Tuple[bytes, bytes]:
    nonce_bytes = b'\x00' * 8 + nonce.to_bytes(4, "little")

    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce_bytes, min_tag_length=8)
    )

    encryptor = cipher.encryptor()

    ciphertext = encryptor.update(payload) + encryptor.finalize()
    tag = encryptor.tag[:8]

    return ciphertext, tag


def _derive_tree_secret(secret: bytes, label: str, generation: int, length: int) -> bytes:
    label_bytes = b"MLS 1.0 " + label.encode("ascii")
    context_bytes = generation.to_bytes(length=4)
    kdf_label = KDFLabel.build({"length": length, "label": label_bytes, "context": context_bytes})
    return HKDFExpand(algorithm=hashes.SHA256(), length=length, info=kdf_label).derive(secret)


class KeyRatchet:
    key: bytes
    nonce: bytes
    generation: int

    def __init__(self, base_secret: bytes):
        self.generation = 0
        self.key = _derive_tree_secret(base_secret, "key", 0, 16)

    def get(self, generation: int) -> bytes:
        if generation > 0:
            raise NotImplementedError("No support for generations beyond 0")
        return self.key

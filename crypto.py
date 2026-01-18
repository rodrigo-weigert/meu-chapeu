from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


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
def encrypt_dave(payload: bytes, nonce: bytes, key: bytes) -> Tuple[bytes, bytes]:
    expanded_nonce = b'\x00' * 8 + nonce  # TODO confirm if big or little endian
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(expanded_nonce, min_tag_length=8),
        backend=default_backend()
    )

    encryptor = cipher.encryptor()

    ciphertext = encryptor.update(payload) + encryptor.finalize()
    tag = encryptor.tag[:8]

    return ciphertext, tag


# TODO verify if this function is correct
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
        full_nonce = _derive_tree_secret(base_secret, "nonce", 0, 12)  # TODO what if I just generate with length 4?
        self.nonce = full_nonce[-4:]  # big endian

    def get(self, generation: int) -> Tuple[bytes, bytes]:
        if generation > 0:
            raise NotImplementedError("No support for generations beyond 0")
        return self.key, self.nonce

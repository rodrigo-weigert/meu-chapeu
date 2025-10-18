from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_packet(header: bytes, payload: bytes, nonce: int, key: bytes, mode: str) -> bytes:
    match mode:
        case "aead_xchacha20_poly1305_rtpsize":
            return crypto_aead_xchacha20poly1305_ietf_encrypt(payload, header, nonce.to_bytes(24, "little"), key)

        case "aead_aes256_gcm_rtpsize":
            return AESGCM(key).encrypt(nonce.to_bytes(12, "little"), payload, header)

        case _:
            raise Exception(f"Unimplemented transport encryption mode: {mode}")

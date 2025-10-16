from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt


def encrypt_packet(header: bytes, payload: bytes, nonce: int, key: bytes):
    encrypted = crypto_aead_xchacha20poly1305_ietf_encrypt(payload, header, nonce.to_bytes(24, "little"), key)
    return encrypted

from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt, crypto_aead_xchacha20poly1305_ietf_decrypt


def decrypt_packet(header: bytes, ciphertext: bytes, nonce: int, key: bytes) -> bytes:
    return crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, header, nonce.to_bytes(24, "little"), key)


def encrypt_packet(header: bytes, payload: bytes, nonce: int, key: bytes) -> bytes:
    encrypted = crypto_aead_xchacha20poly1305_ietf_encrypt(payload, header, nonce.to_bytes(24, "little"), key)
    # assert len(encrypted) == len(payload) + 16
    # assert payload == decrypt_packet(header, encrypted, nonce, key)
    return encrypted

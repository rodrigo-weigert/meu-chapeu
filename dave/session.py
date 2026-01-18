import crypto
import openmls_dave

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalSender:
    identity: bytes
    signature: bytes


@dataclass(frozen=True)
class MediaKey:
    key: bytes
    nonce: bytes


class DaveSessionManager:
    dave_session: openmls_dave.DaveSession
    key_ratchet: crypto.KeyRatchet | None
    external_sender: ExternalSender | None

    def __init__(self, user_id: str):
        self.dave_session = openmls_dave.DaveSession(user_id)
        self.key_rachet = None
        self.external_sender = None

    def get_key_package_message(self) -> bytes:
        return self.dave_session.get_key_package_message()

    def set_external_sender(self, external_sender: ExternalSender):
        self.external_sender = external_sender

    def init_from_welcome(self, welcome: bytes):
        if self.external_sender is None:
            raise Exception("Cannot initialize Dave Session without external sender. Set external sender by calling to set_external_sender()")

        self.dave_session.init_mls_group(self.external_sender.identity, self.external_sender.signature, welcome)
        self.key_ratchet = crypto.KeyRatchet(self.dave_session.export_base_sender_key())

    def get_media_key(self, generation=0) -> MediaKey:
        if self.key_ratchet is None:
            raise Exception("Cannot obtain media key without key ratchet. Make sure instance is initialized by calling one of the init methods")

        key, nonce = self.key_ratchet.get(generation)
        return MediaKey(key=key, nonce=nonce)

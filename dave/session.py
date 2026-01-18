import crypto
import openmls_dave

from dataclasses import dataclass
from enum import Enum, unique, auto

@dataclass(frozen=True)
class ExternalSender:
    identity: bytes
    signature: bytes


@dataclass(frozen=True)
class MediaKey:
    key: bytes
    nonce: bytes


class DaveException(Exception):
    pass


@unique
class TransitionType(Enum):
    WELCOME = auto()


@dataclass(frozen=True)
class Transition:
    transition_type: TransitionType
    transition_id: int
    external_sender: ExternalSender
    mls_data: bytes


class DaveSessionManager:
    dave_session: openmls_dave.DaveSession
    key_ratchet: crypto.KeyRatchet | None
    external_sender: ExternalSender | None
    _pending_transition: Transition | None

    def __init__(self, user_id: str):
        self.dave_session = openmls_dave.DaveSession(user_id)
        self.key_rachet = None
        self.external_sender = None
        self._pending_transition = None

    def get_key_package_message(self) -> bytes:
        return self.dave_session.get_key_package_message()

    def set_external_sender(self, external_sender: ExternalSender):
        self.external_sender = external_sender

    def stage_transition_from_welcome(self, transition_id: int, welcome: bytes):
        if self.external_sender is None:
            raise DaveException(f"Cannot stage transition with id {transition_id}: missing external sender.")

        self._pending_transition = Transition(TransitionType.WELCOME, transition_id, self.external_sender, welcome)

    def execute_transition(self, transition_id: int):
        if self._pending_transition is None:
            raise DaveException("No pending transition to execute")

        if transition_id != self._pending_transition.transition_id:
            raise DaveException(f"Tried to execute unexpected transition with id {transition_id}. Pending transition id was {self._pending_transition.transition_id}")

        if self._pending_transition.transition_type == TransitionType.WELCOME:
            self.dave_session.init_mls_group(self._pending_transition.external_sender.identity, self._pending_transition.external_sender.signature, self._pending_transition.mls_data)
        else:
            raise DaveException(f"Unsupported transition type: {self._pending_transition.transition_type}")

        self.key_ratchet = crypto.KeyRatchet(self.dave_session.export_base_sender_key())
        self._pending_transition = None

    def session_is_active(self) -> bool:
        return self.key_ratchet is not None

    def get_media_key(self, generation=0) -> MediaKey:
        if self.key_ratchet is None:
            raise DaveException("Cannot derive media key: missing key ratchet. Make sure instance is initialized by calling one of the init methods.")

        key, nonce = self.key_ratchet.get(generation)
        return MediaKey(key=key, nonce=nonce)

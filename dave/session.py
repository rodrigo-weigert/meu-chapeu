import crypto
import openmls_dave

from dataclasses import dataclass
from enum import Enum, unique, auto
from typing import Tuple


@dataclass(frozen=True)
class ExternalSender:
    identity: bytes
    signature: bytes


@dataclass(frozen=True)
class MediaKey:
    key: bytes
    nonce: int


class DaveException(Exception):
    pass


@unique
class TransitionType(Enum):
    WELCOME = auto()
    COMMIT = auto()


@dataclass(frozen=True)
class Transition:
    transition_type: TransitionType
    transition_id: int
    external_sender: ExternalSender
    mls_data: bytes


class DaveSessionManager:
    _dave_session: openmls_dave.DaveSession
    _key_ratchet: crypto.KeyRatchet | None
    _external_sender: ExternalSender | None
    _nonce: int
    _pending_transition: Transition | None
    _group_is_established: bool

    def __init__(self, user_id: str):
        self._dave_session = openmls_dave.DaveSession(user_id)
        self._key_ratchet = None
        self._external_sender = None
        self._nonce = 0
        self._pending_transition = None
        self._group_is_established = False

    def get_key_package_message(self) -> bytes:
        return self._dave_session.get_key_package_message()

    def set_external_sender(self, identity: bytes, signature: bytes):
        self._external_sender = ExternalSender(identity, signature)

    def stage_transition_from_welcome(self, transition_id: int, welcome: bytes):
        if self._external_sender is None:
            raise DaveException(f"Cannot stage welcome transition with id {transition_id}: missing external sender")

        self._pending_transition = Transition(TransitionType.WELCOME, transition_id, self._external_sender, welcome)

    def execute_transition(self, transition_id: int):
        if self._pending_transition is None:
            raise DaveException("No pending transition to execute")

        if transition_id != self._pending_transition.transition_id:
            raise DaveException(f"Tried to execute unexpected transition with id {transition_id}. Pending transition id was {self._pending_transition.transition_id}")

        match self._pending_transition.transition_type:
            case TransitionType.WELCOME:
                self._dave_session.init_mls_group(self._pending_transition.external_sender.identity, self._pending_transition.external_sender.signature, self._pending_transition.mls_data)
                self._group_is_established = True
            case TransitionType.COMMIT:
                pass
            case _:
                raise DaveException(f"Unsupported transition type: {self._pending_transition.transition_type}")

        self._key_ratchet = crypto.KeyRatchet(self._dave_session.export_base_sender_key())
        self._pending_transition = None

    def get_current_media_key(self) -> MediaKey | None:
        kr = self._key_ratchet
        if kr is None:
            return None

        nonce, generation = self._get_and_advance_nonce()
        return MediaKey(key=kr.get(generation), nonce=nonce)

    def append_proposals(self, proposal_message: bytes) -> bytes:
        if self._group_is_established:
            result = self._dave_session.append_proposals(proposal_message)
        elif self._external_sender is not None:  # Initial group creation
            result = self._dave_session.append_proposals_local_group(proposal_message, self._external_sender.identity, self._external_sender.signature)
        else:
            raise DaveException("Cannot process proposals using local MLS group: missing external sender")

        if result.welcome is not None:
            return result.commit + result.welcome
        return result.commit

    def stage_transition_from_commit(self, transition_id: int, commit: bytes):
        assert self._external_sender is not None
        self._pending_transition = Transition(TransitionType.COMMIT, transition_id, self._external_sender, commit)
        self._dave_session.merge_commit(commit)

    def _get_and_advance_nonce(self) -> Tuple[int, int]:
        current_nonce = self._nonce & 0xFFFFFFFF
        current_gen = self._nonce >> 24
        self._nonce += 1
        return current_nonce, current_gen

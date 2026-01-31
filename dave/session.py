import crypto
import openmls_dave  # type: ignore[import-untyped]

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


@dataclass(frozen=True)
class Transition:
    transition_id: int


@dataclass(frozen=True)
class WelcomeTransition(Transition):
    data: bytes
    external_sender: ExternalSender  # TODO: this attribute is probably unnecessary - remove and simplify ES logic


@dataclass(frozen=True)
class CommitTransition(Transition):
    data: bytes


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

        self._pending_transition = WelcomeTransition(transition_id=transition_id, data=welcome, external_sender=self._external_sender)

    def execute_transition(self, transition_id: int):
        if self._pending_transition is None:
            raise DaveException("No pending transition to execute")

        if transition_id != self._pending_transition.transition_id:
            raise DaveException(f"Tried to execute unexpected transition with id {transition_id}. Pending transition was {self._pending_transition}")

        match self._pending_transition:
            case WelcomeTransition(data=welcome_data, external_sender=es):
                self._dave_session.init_mls_group(es.identity, es.signature, welcome_data)
                self._group_is_established = True
            case CommitTransition():
                pass
            case _:
                raise DaveException(f"Unsupported transition type: {self._pending_transition}")

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
        self._pending_transition = CommitTransition(transition_id=transition_id, data=commit)
        self._dave_session.merge_commit(commit)

    def _get_and_advance_nonce(self) -> Tuple[int, int]:
        current_nonce = self._nonce & 0xFFFFFFFF
        current_gen = self._nonce >> 24
        self._nonce += 1
        return current_nonce, current_gen

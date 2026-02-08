import openmls_dave  # type: ignore[import-untyped]

from crypto import KeyRatchet
from dataclasses import dataclass, field
from enum import Enum, unique, auto
from typing import Tuple, Dict


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


class DaveInvalidCommitException(DaveException):
    pass


@unique
class TransitionType(Enum):
    WELCOME = auto()
    COMMIT = auto()
    DOWNGRADE = auto()


@dataclass(frozen=True)
class Transition:
    id: int
    type: TransitionType
    key_ratchet: KeyRatchet | None = field(repr=False)


class DaveSessionManager:
    _user_id: str
    _dave_session: openmls_dave.DaveSession
    _key_ratchet: KeyRatchet | None
    _external_sender: ExternalSender | None
    _nonce: int
    _pending_transitions: Dict[int, Transition]
    _invalidated: bool

    def __init__(self, user_id: str):
        self._user_id = user_id
        self._dave_session = openmls_dave.DaveSession(user_id)
        self._key_ratchet = None
        self._external_sender = None
        self._nonce = 0
        self._pending_transitions = dict()
        self._invalidated = False

    def get_key_package_message(self) -> bytes:
        return self._dave_session.get_key_package_message()

    def set_external_sender(self, identity: bytes, signature: bytes):
        self._external_sender = ExternalSender(identity, signature)

    def stage_transition_from_welcome(self, transition_id: int, welcome: bytes):
        if self._external_sender is None:
            raise DaveException(f"Cannot stage welcome transition with id {transition_id}: missing external sender")

        self._dave_session.create_group_from_welcome(self._external_sender.identity, self._external_sender.signature, welcome)
        self._add_transition(transition_id, TransitionType.WELCOME)

    def execute_transition(self, transition_id: int) -> TransitionType | None:
        transition = self._pending_transitions.pop(transition_id, None)

        if transition is None:
            return None

        if self._invalidated and transition.type != TransitionType.WELCOME:
            return None

        self._key_ratchet = transition.key_ratchet

        if transition.type == TransitionType.WELCOME:
            self._invalidated = False

        return transition.type

    def get_current_media_key(self) -> MediaKey | None:
        kr = self._key_ratchet
        if kr is None:
            return None

        nonce, generation = self._get_and_advance_nonce()
        return MediaKey(key=kr.get(generation), nonce=nonce)

    def append_proposals(self, proposal_message: bytes) -> bytes | None:
        if self._invalidated:
            return None

        if self._dave_session.mls_group_exists():
            result = self._dave_session.append_proposals(proposal_message)
        elif self._external_sender is not None:  # Initial group creation
            result = self._dave_session.create_group_and_append_proposals(proposal_message, self._external_sender.identity, self._external_sender.signature)
        else:
            raise DaveException("Cannot process proposals using local MLS group: missing external sender")

        if result.welcome is not None:
            return result.commit + result.welcome
        return result.commit

    def stage_transition_from_commit(self, transition_id: int, commit: bytes):
        assert self._external_sender is not None

        try:
            self._dave_session.merge_commit(commit)
        except openmls_dave.DaveInvalidCommit as e:
            self._invalidated = True
            raise DaveInvalidCommitException(str(e)) from None

        self._add_transition(transition_id, TransitionType.COMMIT)

    def stage_downgrade_transition(self, transition_id: int):
        self._add_transition(transition_id, TransitionType.DOWNGRADE)

    def reset_session(self):
        self._dave_session = openmls_dave.DaveSession(self._user_id)
        self._nonce = 0
        self._pending_transitions.clear()

    def _get_and_advance_nonce(self) -> Tuple[int, int]:
        current_nonce = self._nonce & 0xFFFFFFFF
        current_gen = self._nonce >> 24
        self._nonce += 1
        return current_nonce, current_gen

    def _key_ratchet_from_current_state(self) -> KeyRatchet:
        return KeyRatchet(self._dave_session.export_base_sender_key())

    def _add_transition(self, transition_id: int, transition_type: TransitionType):
        kr = self._key_ratchet_from_current_state() if transition_type != TransitionType.DOWNGRADE else None
        self._pending_transitions[transition_id] = Transition(transition_id, transition_type, kr)

import json
import dave.parser

from enum import Enum, unique
from typing import Dict, Any


@unique
class VoiceOpCode(Enum):
    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HEARTBEAT_ACK = 6
    HELLO = 8
    CLIENTS_CONNECT = 11
    CLIENTS_DISCONNECT = 13
    DAVE_PREPARE_TRANSITION = 21
    DAVE_EXECUTE_TRANSITION = 22
    DAVE_TRANSITION_READY = 23
    DAVE_PREPARE_EPOCH = 24
    DAVE_MLS_EXTERNAL_SENDER = 25
    DAVE_MLS_KEY_PACKAGE = 26
    DAVE_MLS_PROPOSALS = 27
    DAVE_MLS_COMMIT_WELCOME = 28
    DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION = 29
    DAVE_MLS_WELCOME = 30
    DAVE_MLS_INVALID_COMMIT_WELCOME = 31
    UNKNOWN = 99

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class VoiceEvent:
    _opcode: VoiceOpCode
    _seq_num: int | None
    _parsed: Dict[str, Any]
    _binary: bool

    def __init__(self, raw: str | bytes) -> None:
        if isinstance(raw, str):
            parsed = json.loads(raw)
            self._opcode = VoiceOpCode(parsed["op"])
            self._seq_num = parsed.get("seq")
            self._parsed = parsed.get("d", {})
            self._binary = False
        else:
            parsed = dave.parser.DAVE_Message.parse(raw)
            self._opcode = VoiceOpCode(parsed.opcode)
            self._seq_num = parsed.get("sequence_number")
            self._parsed = parsed.data
            self._binary = True

    @property
    def opcode(self) -> VoiceOpCode:
        return self._opcode

    @property
    def seq_num(self) -> int | None:
        return self._seq_num

    def __getitem__(self, key: str) -> Any:
        return self._parsed[key]

    def __str__(self) -> str:
        if self._binary:
            return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Binary fields: {[k for k in self._parsed.keys() if not k.startswith("_")]}"
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Data: {self._parsed}"

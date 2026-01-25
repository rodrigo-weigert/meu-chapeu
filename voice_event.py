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
    opcode: VoiceOpCode
    name: str | None
    seq_num: int | None
    _parsed: Dict[str, Any]
    binary: bool

    def __init__(self, raw: str | bytes):
        if isinstance(raw, str):
            self._parsed = json.loads(raw)
            self.opcode = VoiceOpCode(self._parsed["op"])
            self.seq_num = self._parsed.get("seq")
            self.binary = False
        else:
            parsed = dave.parser.DAVE_Message.parse(raw)
            self.seq_num = parsed.get("sequence_number")
            self.opcode = VoiceOpCode(parsed.opcode)
            self._parsed = {"d": parsed.data}
            self.binary = True

    def get(self, prop: str) -> Any:
        return self._parsed["d"].get(prop)

    def __str__(self):
        if self.binary:
            return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Parsed binary fields: {[k for k in self._parsed["d"].keys() if not k.startswith("_")]}"
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Raw: {self._parsed}"

import json

from enum import Enum, unique
from typing import Dict, Any


@unique
class VoiceOpCode(Enum):
    IDENTIFY = 0
    READY = 2
    HEARTBEAT = 3
    HEARTBEAT_ACK = 6
    HELLO = 8
    UNKNOWN = 99

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class VoiceEvent:
    opcode: VoiceOpCode
    name: str | None
    seq_num: int | None
    _parsed: Dict[str, Any]

    def __init__(self, raw):
        self._parsed = json.loads(raw)
        self.opcode = VoiceOpCode(self._parsed["op"])
        self.seq_num = self._parsed.get("seq")

    def get(self, prop: str) -> Any:
        return self._parsed["d"].get(prop)

    def __str__(self):
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Raw: {self._parsed}"

import json

from enum import Enum, unique
from typing import Dict, Any


@unique
class OpCode(Enum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    VOICE_STATE_UPDATE = 4
    HELLO = 10
    HEARTBEAT_ACK = 11


class Event:
    opcode: OpCode
    name: str | None
    seq_num: int | None
    _parsed: Dict[str, Any]

    def __init__(self, raw):
        self._parsed = json.loads(raw)
        self.opcode = OpCode(self._parsed["op"])
        self.name = self._parsed["t"]
        self.seq_num = self._parsed["s"]

    def get(self, prop: str) -> Any:
        return self._parsed["d"][prop] if prop in self._parsed["d"] else None

    def __str__(self):
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Name: {self.name}, Raw: {self._parsed}"

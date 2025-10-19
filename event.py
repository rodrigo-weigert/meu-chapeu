import json

from enum import Enum, unique
from typing import Dict, Any


@unique
class OpCode(Enum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    INVALID_SESSION = 9
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
        self.name = self._parsed.get("t")
        self.seq_num = self._parsed.get("s")

    def get(self, prop: str) -> Any:
        return self._parsed["d"].get(prop)

    def __str__(self):
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Name: {self.name}, Raw: {self._parsed}"

import json

from enum import Enum, unique
from typing import Dict, Any

@unique
class OpCode(Enum):
    DISPATCH = 0
    HEARTBEAT = 1
    HELLO = 10
    HEARTBEAT_ACK = 11

class Event:
    opcode: OpCode
    _parsed: Dict[str, Any]

    def __init__(self, raw):
        self._parsed = json.loads(raw)
        self.opcode = OpCode(self._parsed["op"])

    def get(self, prop):
        return self._parsed["d"][prop]

    def seq_num(self):
        return self._parsed["s"]

    def __str__(self):
        return f"Opcode: {self.opcode}, Seq: {self.seq_num()}, Raw: {self._parsed}"

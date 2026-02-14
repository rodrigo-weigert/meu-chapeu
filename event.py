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
    _opcode: OpCode
    _seq_num: int | None
    _name: str | None
    _parsed: Dict[str, Any]

    def __init__(self, raw: str) -> None:
        parsed = json.loads(raw)
        self._opcode = OpCode(parsed["op"])
        self._seq_num = parsed.get("s")
        self._name = parsed.get("t")
        self._parsed = parsed["d"]

    @property
    def opcode(self) -> OpCode:
        return self._opcode

    @property
    def seq_num(self) -> int | None:
        return self._seq_num

    @property
    def name(self) -> str | None:
        return self._name

    def __getitem__(self, key: str) -> Any:
        return self._parsed[key]

    def __str__(self) -> str:
        return f"Opcode: {self.opcode}, Seq: {self.seq_num}, Name: {self.name}, Data: {self._parsed}"

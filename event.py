import json

from enum import Enum, unique

@unique
class EventType(Enum):
    HELLO = 10
    HEARTBEAT_ACK = 11

class Event:
    event_type: EventType

    def __init__(self, raw):
        self._parsed = json.loads(raw)
        self.event_type = EventType(self._parsed["op"])

    def get(self, prop):
        return self._parsed["d"][prop]

    def __str__(self):
        return f"Event type: {self.event_type}, raw: {self._parsed}"

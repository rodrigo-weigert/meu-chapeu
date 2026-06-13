from enum import IntEnum

__all__ = ["InteractionFlag", "build_string_response"]


class InteractionType(IntEnum):
    CHANNEL_MESSAGE_WITH_SOURCE = 4


class InteractionFlag(IntEnum):
    SUPPRESS_EMBEDS = 1 << 2
    EPHEMERAL = 1 << 6


def build_string_response(message: str, flags: int = 0):
    return {"type": InteractionType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": message,
                     "flags": flags}}

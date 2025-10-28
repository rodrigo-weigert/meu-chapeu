class InteractionType:
    CHANNEL_MESSAGE_WITH_SOURCE: int = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: int = 5


class InteractionFlag:
    SUPRESS_EMBEDS: int = 1 << 2
    EPHEMERAL: int = 1 << 6
    SUPPRESS_NOTIFICATIONS: int = 1 << 12

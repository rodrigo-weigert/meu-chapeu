from construct import (FocusedSeq, Int8ub, Bytes, this, Switch, Int16ub, Struct,
                       GreedyBytes, If, Default, Adapter, Rebuild, len_)


class _ParseLengthHeader(Adapter):
    def _decode(self, obj, ctx, path):
        prefix = obj.first_byte >> 6
        rest = obj.first_byte & ((1 << 6)-1)

        if prefix == 0:
            return rest
        if prefix == 1:
            return (rest << 8) | int.from_bytes(obj.remaining_bytes)
        if prefix == 2:
            return (rest << 24) | int.from_bytes(obj.remaining_bytes)

        raise ValueError("Invalid length header")

    def _encode(self, obj, ctx, path):
        if obj < (1 << 6):
            return {"first_byte": obj,
                    "remaining_bytes": None}
        elif obj < (1 << 14):
            return {"first_byte": (obj >> 8) | 0x40,
                    "remaining_bytes": (obj & ((1 << 8) - 1)).to_bytes(length=1)}
        elif obj < (1 << 30):
            return {"first_byte": (obj >> 24) | 0x80,
                    "remaining_bytes": (obj & ((1 << 24) - 1)).to_bytes(length=3, byteorder="big")}

        raise ValueError("Length exceeds Vector limit")


_LengthHeader = Struct(
    "first_byte" / Int8ub,
    "remaining_bytes" / Default(If((this.first_byte >> 6) > 0, Switch(this.first_byte >> 6, {1: Bytes(1),
                                                                                             2: Bytes(3)})),
                                b'\x00'),
)

LengthHeader = _ParseLengthHeader(_LengthHeader)

Vector = FocusedSeq(
    "data",
    "length" / Rebuild(LengthHeader, len_(this.data)),
    "data" / Bytes(this.length)
)

Credential = Struct(
        "credential_type" / Int16ub,
        "identity" / Vector
)

ExternalSender = Struct(
        "signature_key" / Vector,
        "credential" / Credential
)

DAVE_MLSExternalSenderPackage_Body = Struct(
    "external_sender" / ExternalSender
)

DAVE_MLSWelcome_Body = Struct(
    "transition_id" / Int16ub,
    "welcome_message" / GreedyBytes
)

DAVE_MLSAnnounceCommitTransition_Body = Struct(
    "transition_id" / Int16ub,
    "commit_message" / GreedyBytes
)

DAVE_MLSProposals_Body = Struct(
    "operation_type" / Int8ub,
    "proposal_messages" / If(this.operation_type == 0, Vector),
    "proposal_refs" / If(this.operation_type == 1, Vector)
)

DAVE_Message = Struct(
    "sequence_number" / Int16ub,
    "opcode" / Int8ub,
    "data" / Switch(this.opcode, {25: DAVE_MLSExternalSenderPackage_Body,
                                  27: DAVE_MLSProposals_Body,
                                  29: DAVE_MLSAnnounceCommitTransition_Body,
                                  30: DAVE_MLSWelcome_Body})
)

KDFLabel = Struct(
    "length" / Int16ub,
    "label" / Vector,
    "context" / Vector
)

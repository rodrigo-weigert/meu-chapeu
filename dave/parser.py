from construct import FocusedSeq, Int8ub, Bytes, this, Peek, BitsInteger, Switch, Int16ub, Int32ub, Struct, BitStruct, GreedyBytes, If

_Vector1 = FocusedSeq(
    "data",
    "length" / Int8ub,
    "data" / Bytes(this.length)
)

_Vector2 = FocusedSeq(
    "data",
    "length" / Int16ub,
    "data" / Bytes(this.length & ((1 << 14)-1))
)

_Vector4 = FocusedSeq(
    "data",
    "length" / Int32ub,
    "data" / Bytes(this.length & ((1 << 30)-1))
)

LengthBytePeek = Peek(BitStruct(
    "prefix" / BitsInteger(2),
    BitsInteger(6)
))

Vector = FocusedSeq(
    "data",
    "first_length_byte" / LengthBytePeek,
    "data" / Switch(this.first_length_byte.prefix, {0: _Vector1,
                                                    1: _Vector2,
                                                    2: _Vector4}))

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
    "transition_id" / Int16ub,
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

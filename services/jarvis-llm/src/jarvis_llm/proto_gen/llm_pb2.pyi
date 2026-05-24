import common_pb2 as _common_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class IntentClass(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    INTENT_UNSPECIFIED: _ClassVar[IntentClass]
    INTENT_SIMPLE: _ClassVar[IntentClass]
    INTENT_CONVERSATIONAL: _ClassVar[IntentClass]
    INTENT_COMPLEX: _ClassVar[IntentClass]
    INTENT_CODE: _ClassVar[IntentClass]
    INTENT_TOOL_USE: _ClassVar[IntentClass]

class RouteTarget(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TARGET_UNSPECIFIED: _ClassVar[RouteTarget]
    TARGET_LOCAL: _ClassVar[RouteTarget]
    TARGET_CLOUD: _ClassVar[RouteTarget]
INTENT_UNSPECIFIED: IntentClass
INTENT_SIMPLE: IntentClass
INTENT_CONVERSATIONAL: IntentClass
INTENT_COMPLEX: IntentClass
INTENT_CODE: IntentClass
INTENT_TOOL_USE: IntentClass
TARGET_UNSPECIFIED: RouteTarget
TARGET_LOCAL: RouteTarget
TARGET_CLOUD: RouteTarget

class PingRequest(_message.Message):
    __slots__ = ("client_id",)
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    def __init__(self, client_id: _Optional[str] = ...) -> None: ...

class PingResponse(_message.Message):
    __slots__ = ("status", "version")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    status: _common_pb2.Status
    version: str
    def __init__(self, status: _Optional[_Union[_common_pb2.Status, _Mapping]] = ..., version: _Optional[str] = ...) -> None: ...

class CompleteRequest(_message.Message):
    __slots__ = ("prompt", "intent", "max_tokens", "system_prompt", "client_id")
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    INTENT_FIELD_NUMBER: _ClassVar[int]
    MAX_TOKENS_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    prompt: str
    intent: IntentClass
    max_tokens: int
    system_prompt: str
    client_id: str
    def __init__(self, prompt: _Optional[str] = ..., intent: _Optional[_Union[IntentClass, str]] = ..., max_tokens: _Optional[int] = ..., system_prompt: _Optional[str] = ..., client_id: _Optional[str] = ...) -> None: ...

class CompleteResponse(_message.Message):
    __slots__ = ("status", "text", "target", "model", "input_tokens", "output_tokens", "reason")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    INPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    status: _common_pb2.Status
    text: str
    target: RouteTarget
    model: str
    input_tokens: int
    output_tokens: int
    reason: str
    def __init__(self, status: _Optional[_Union[_common_pb2.Status, _Mapping]] = ..., text: _Optional[str] = ..., target: _Optional[_Union[RouteTarget, str]] = ..., model: _Optional[str] = ..., input_tokens: _Optional[int] = ..., output_tokens: _Optional[int] = ..., reason: _Optional[str] = ...) -> None: ...

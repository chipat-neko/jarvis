import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Status(_message.Message):
    __slots__ = ("code", "message")
    class Code(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN: _ClassVar[Status.Code]
        OK: _ClassVar[Status.Code]
        ERROR: _ClassVar[Status.Code]
        TIMEOUT: _ClassVar[Status.Code]
        UNAUTHORIZED: _ClassVar[Status.Code]
    UNKNOWN: Status.Code
    OK: Status.Code
    ERROR: Status.Code
    TIMEOUT: Status.Code
    UNAUTHORIZED: Status.Code
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: Status.Code
    message: str
    def __init__(self, code: _Optional[_Union[Status.Code, str]] = ..., message: _Optional[str] = ...) -> None: ...

class TraceContext(_message.Message):
    __slots__ = ("trace_id", "span_id", "started_at")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    started_at: _timestamp_pb2.Timestamp
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

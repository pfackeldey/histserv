from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class InitRequest(_message.Message):
    __slots__ = ("hist_json",)
    HIST_JSON_FIELD_NUMBER: _ClassVar[int]
    hist_json: str
    def __init__(self, hist_json: _Optional[str] = ...) -> None: ...

class InitResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class FillRequest(_message.Message):
    __slots__ = ("hist_id", "kwargs")
    class KwargsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Value
        def __init__(
            self,
            key: _Optional[str] = ...,
            value: _Optional[_Union[Value, _Mapping]] = ...,
        ) -> None: ...

    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    KWARGS_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    kwargs: _containers.MessageMap[str, Value]
    def __init__(
        self,
        hist_id: _Optional[str] = ...,
        kwargs: _Optional[_Mapping[str, Value]] = ...,
    ) -> None: ...

class FillResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class SnapShotRequest(_message.Message):
    __slots__ = ("hist_id", "drop_from_server")
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    DROP_FROM_SERVER_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    drop_from_server: bool
    def __init__(
        self, hist_id: _Optional[str] = ..., drop_from_server: bool = ...
    ) -> None: ...

class SnapShotResponse(_message.Message):
    __slots__ = ("success", "message", "hist_json", "data")
    class DataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Value
        def __init__(
            self,
            key: _Optional[str] = ...,
            value: _Optional[_Union[Value, _Mapping]] = ...,
        ) -> None: ...

    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    HIST_JSON_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    hist_json: str
    data: _containers.MessageMap[str, Value]
    def __init__(
        self,
        success: bool = ...,
        message: _Optional[str] = ...,
        hist_json: _Optional[str] = ...,
        data: _Optional[_Mapping[str, Value]] = ...,
    ) -> None: ...

class FlushRequest(_message.Message):
    __slots__ = ("hist_id", "destination")
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    DESTINATION_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    destination: str
    def __init__(
        self, hist_id: _Optional[str] = ..., destination: _Optional[str] = ...
    ) -> None: ...

class FlushResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class Dtype(_message.Message):
    __slots__ = ("type",)
    class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TYPE_DT_FLOAT32: _ClassVar[Dtype.Type]
        TYPE_DT_FLOAT64: _ClassVar[Dtype.Type]
        TYPE_DT_INT32: _ClassVar[Dtype.Type]
        TYPE_DT_INT64: _ClassVar[Dtype.Type]

    TYPE_DT_FLOAT32: Dtype.Type
    TYPE_DT_FLOAT64: Dtype.Type
    TYPE_DT_INT32: Dtype.Type
    TYPE_DT_INT64: Dtype.Type
    TYPE_FIELD_NUMBER: _ClassVar[int]
    type: Dtype.Type
    def __init__(self, type: _Optional[_Union[Dtype.Type, str]] = ...) -> None: ...

class Ndarray(_message.Message):
    __slots__ = ("shape", "dtype", "data")
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    DTYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    shape: _containers.RepeatedScalarFieldContainer[int]
    dtype: Dtype
    data: bytes
    def __init__(
        self,
        shape: _Optional[_Iterable[int]] = ...,
        dtype: _Optional[_Union[Dtype, _Mapping]] = ...,
        data: _Optional[bytes] = ...,
    ) -> None: ...

class Value(_message.Message):
    __slots__ = ("array_value", "string_value", "int_value", "bool_value")
    ARRAY_VALUE_FIELD_NUMBER: _ClassVar[int]
    STRING_VALUE_FIELD_NUMBER: _ClassVar[int]
    INT_VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOL_VALUE_FIELD_NUMBER: _ClassVar[int]
    array_value: Ndarray
    string_value: str
    int_value: int
    bool_value: bool
    def __init__(
        self,
        array_value: _Optional[_Union[Ndarray, _Mapping]] = ...,
        string_value: _Optional[str] = ...,
        int_value: _Optional[int] = ...,
        bool_value: bool = ...,
    ) -> None: ...

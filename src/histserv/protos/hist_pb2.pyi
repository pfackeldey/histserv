import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
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
    __slots__ = ("hist_id",)
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    def __init__(self, hist_id: _Optional[str] = ...) -> None: ...

class ExistsRequest(_message.Message):
    __slots__ = ("hist_id",)
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    def __init__(self, hist_id: _Optional[str] = ...) -> None: ...

class ExistsResponse(_message.Message):
    __slots__ = ("exists",)
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    exists: bool
    def __init__(self, exists: bool = ...) -> None: ...

class FillRequest(_message.Message):
    __slots__ = ("hist_id", "unique_id", "kwargs")
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
    UNIQUE_ID_FIELD_NUMBER: _ClassVar[int]
    KWARGS_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    unique_id: str
    kwargs: _containers.MessageMap[str, Value]
    def __init__(
        self,
        hist_id: _Optional[str] = ...,
        unique_id: _Optional[str] = ...,
        kwargs: _Optional[_Mapping[str, Value]] = ...,
    ) -> None: ...

class FillResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SnapshotRequest(_message.Message):
    __slots__ = ("hist_id", "delete_from_server")
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    DELETE_FROM_SERVER_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    delete_from_server: bool
    def __init__(
        self, hist_id: _Optional[str] = ..., delete_from_server: bool = ...
    ) -> None: ...

class SnapshotResponse(_message.Message):
    __slots__ = ("hist_json", "data")
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

    HIST_JSON_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    hist_json: str
    data: _containers.MessageMap[str, Value]
    def __init__(
        self,
        hist_json: _Optional[str] = ...,
        data: _Optional[_Mapping[str, Value]] = ...,
    ) -> None: ...

class DeleteRequest(_message.Message):
    __slots__ = ("hist_id",)
    HIST_ID_FIELD_NUMBER: _ClassVar[int]
    hist_id: str
    def __init__(self, hist_id: _Optional[str] = ...) -> None: ...

class DeleteResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

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
    __slots__ = ()
    def __init__(self) -> None: ...

class StatsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StatsResponse(_message.Message):
    __slots__ = (
        "histogram_count",
        "histogram_bytes",
        "active_rpcs",
        "version",
        "uptime_seconds",
        "user_cpu_seconds",
        "system_cpu_seconds",
        "rpc_calls_total",
        "observed_at",
        "token_scoped",
    )
    class RpcCallsTotalEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(
            self, key: _Optional[str] = ..., value: _Optional[int] = ...
        ) -> None: ...

    HISTOGRAM_COUNT_FIELD_NUMBER: _ClassVar[int]
    HISTOGRAM_BYTES_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_RPCS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    USER_CPU_SECONDS_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_CPU_SECONDS_FIELD_NUMBER: _ClassVar[int]
    RPC_CALLS_TOTAL_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    TOKEN_SCOPED_FIELD_NUMBER: _ClassVar[int]
    histogram_count: int
    histogram_bytes: int
    active_rpcs: int
    version: str
    uptime_seconds: int
    user_cpu_seconds: float
    system_cpu_seconds: float
    rpc_calls_total: _containers.ScalarMap[str, int]
    observed_at: _timestamp_pb2.Timestamp
    token_scoped: TokenScopedStats
    def __init__(
        self,
        histogram_count: _Optional[int] = ...,
        histogram_bytes: _Optional[int] = ...,
        active_rpcs: _Optional[int] = ...,
        version: _Optional[str] = ...,
        uptime_seconds: _Optional[int] = ...,
        user_cpu_seconds: _Optional[float] = ...,
        system_cpu_seconds: _Optional[float] = ...,
        rpc_calls_total: _Optional[_Mapping[str, int]] = ...,
        observed_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
        token_scoped: _Optional[_Union[TokenScopedStats, _Mapping]] = ...,
    ) -> None: ...

class TokenScopedStats(_message.Message):
    __slots__ = ("histogram_count", "histogram_bytes", "rpc_calls_total")
    class RpcCallsTotalEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(
            self, key: _Optional[str] = ..., value: _Optional[int] = ...
        ) -> None: ...

    HISTOGRAM_COUNT_FIELD_NUMBER: _ClassVar[int]
    HISTOGRAM_BYTES_FIELD_NUMBER: _ClassVar[int]
    RPC_CALLS_TOTAL_FIELD_NUMBER: _ClassVar[int]
    histogram_count: int
    histogram_bytes: int
    rpc_calls_total: _containers.ScalarMap[str, int]
    def __init__(
        self,
        histogram_count: _Optional[int] = ...,
        histogram_bytes: _Optional[int] = ...,
        rpc_calls_total: _Optional[_Mapping[str, int]] = ...,
    ) -> None: ...

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

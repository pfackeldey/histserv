from __future__ import annotations

import hashlib
import json
import typing as tp

import numcodecs
import numpy as np

from histserv.protos import hist_pb2

DEFAULT_CODEC = numcodecs.Blosc(
    cname="zstd",
    clevel=1,
    shuffle=numcodecs.Blosc.BITSHUFFLE,
)
COMPRESSION_THRESHOLD_BYTES = 16


def serialize_nparray(item: np.ndarray | list | tuple) -> hist_pb2.Ndarray:
    item = np.ascontiguousarray(item)
    if item.dtype.hasobject:
        raise ValueError(f"object arrays are not supported: {item.dtype=}")
    payload = item.tobytes()
    encoded = (
        payload
        if item.nbytes <= COMPRESSION_THRESHOLD_BYTES
        else DEFAULT_CODEC.encode(payload)
    )
    return hist_pb2.Ndarray(
        shape=list(item.shape),
        dtype=item.dtype.str,
        data=encoded,
    )


def deserialize_nparray(message: hist_pb2.Ndarray) -> np.ndarray:
    shape = tuple(message.shape)
    dtype = np.dtype(message.dtype)
    if dtype.hasobject:
        raise ValueError(f"object arrays are not supported: {dtype=}")
    raw_nbytes = int(np.prod(shape, dtype=np.int64)) * np.dtype(dtype).itemsize
    decoded = (
        message.data
        if len(message.data) == raw_nbytes
        else DEFAULT_CODEC.decode(message.data)
    )
    return np.frombuffer(decoded, dtype=dtype).reshape(shape)


def serialize_proto_Value(item: tp.Any) -> hist_pb2.Value:
    msg = hist_pb2.Value()
    match item:
        case str():
            msg.string_value = item
        case int():
            msg.int_value = item
        case bool():
            msg.bool_value = item
        case _:
            try:
                msg.array_value.CopyFrom(serialize_nparray(item))
            except Exception as exc:  # pragma: no cover - defensive
                raise TypeError(f"Can't serialize: {item=} ({type(item)=})") from exc
    return msg


def deserialize_proto_Value(message: hist_pb2.Value):
    match message.WhichOneof("value"):
        case "array_value":
            return deserialize_nparray(message.array_value)
        case "string_value":
            return message.string_value
        case "int_value":
            return message.int_value
        case "bool_value":
            return message.bool_value
        case _:
            raise ValueError(f"Unsupported Value type, got {message=}")


def serialize_unique_id(unique_id: tp.Any) -> bytes:
    return hashlib.sha256(
        json.dumps(unique_id, sort_keys=True).encode("utf-8")
    ).digest()

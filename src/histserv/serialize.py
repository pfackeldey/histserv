from __future__ import annotations

import hashlib
import json
import typing as tp
from collections.abc import Mapping

import numcodecs
import numpy as np
import uhi.io.json
from hist import Hist
import hist.serialization  # noqa: F401

from histserv.protos import hist_pb2

# hardcode for now, make it configurable later
# TODO: needs to be part of protobuf to allow custom serialization per RPC call
# In multiple local tests the codec with:
# - algo: 'zstd'
# - clevel: 1
# - shuffle: BITSHUFFLE
# yielded the best combination of compression/decompression time and compression
# factor for float32 NanoAOD columns (Electron_mass, Jet_pt, MET_pt, ...)
codec = numcodecs.Blosc(cname="zstd", clevel=1, shuffle=numcodecs.Blosc.BITSHUFFLE)
COMPRESSION_THRESHOLD_BYTES = 1024


def serialize_nparray(item: np.ndarray | list | tuple) -> hist_pb2.Ndarray:
    """Serialize an array-like object into a protobuf ndarray message.

    Args:
        item: Numpy array or array-like input to encode.

    Returns:
        hist_pb2.Ndarray: Protobuf message containing shape, dtype, and encoded
            byte content.

    Raises:
        ValueError: If the numpy dtype cannot be represented in protobuf.

    Example:
        >>> msg = serialize_nparray(np.array([1.0, 2.0], dtype=np.float32))
        >>> list(msg.shape)
        [2]
    """
    item = np.ascontiguousarray(item)

    shape = list(item.shape)
    dtype = _numpy_dtype_to_proto_dtype(item.dtype)

    payload = item.tobytes()
    if item.nbytes <= COMPRESSION_THRESHOLD_BYTES:
        encoded_data = payload
    else:
        encoded_data = codec.encode(payload)

    return hist_pb2.Ndarray(shape=shape, dtype=dtype, data=encoded_data)


def deserialize_nparray(message: hist_pb2.Ndarray) -> np.ndarray:
    """Deserialize a protobuf ndarray message into a NumPy array."""
    shape = tuple(message.shape)
    dtype = _proto_dtype_to_numpy_dtype(message.dtype)
    raw_nbytes = int(np.prod(shape, dtype=np.int64)) * np.dtype(dtype).itemsize

    if len(message.data) == raw_nbytes:
        decoded_data = message.data
    else:
        decoded_data = codec.decode(message.data)

    return np.frombuffer(decoded_data, dtype=dtype).reshape(shape)


def serialize_proto_Value(item: tp.Any) -> hist_pb2.Value:
    """Serialize a scalar or array-like object into a protobuf value message.

    Args:
        item: Supported input value, such as a string, integer, boolean, numpy
            array, or array-like object.

    Returns:
        hist_pb2.Value: Protobuf wrapper containing the serialized value.

    Raises:
        TypeError: If the value cannot be serialized into one of the supported
            protobuf variants.

    Example:
        >>> msg = serialize_proto_Value(np.array([1, 2, 3], dtype=np.int32))
        >>> msg.WhichOneof("value")
        'array_value'
    """
    msg = hist_pb2.Value()
    match item:
        case str():  # StrCategory axis
            msg.string_value = item
        case int():  # IntCategory axis
            msg.int_value = item
        case bool():  # Boolean axis
            msg.bool_value = item
        # all other axes: Integer, Regular, Variable (can this also be Boolean?)
        case _:
            try:
                msg.array_value.CopyFrom(serialize_nparray(item))
            except Exception as e:
                raise TypeError(f"Can't serialize: {item=} ({type(item)=})") from e
    return msg


def _numpy_dtype_to_proto_dtype(np_dtype: np.dtype) -> hist_pb2.Dtype:
    """Mapping from numpy dtypes to hist_pb2.dtype messages."""
    match np_dtype:
        case np.float32:
            return hist_pb2.Dtype(type=hist_pb2.Dtype.TYPE_DT_FLOAT32)
        case np.float64:
            return hist_pb2.Dtype(type=hist_pb2.Dtype.TYPE_DT_FLOAT64)
        case np.int32:
            return hist_pb2.Dtype(type=hist_pb2.Dtype.TYPE_DT_INT32)
        case np.int64:
            return hist_pb2.Dtype(type=hist_pb2.Dtype.TYPE_DT_INT64)
        case _:
            raise ValueError(f"Unsupported numpy dtype: {np_dtype=}")


def deserialize_proto_Value(message: hist_pb2.Value):
    """Deserialize a protobuf value message into a Python object.

    Args:
        message: Protobuf value message produced by `serialize_proto_Value`.

    Returns:
        tp.Any: Deserialized numpy array, string, integer, or boolean value.

    Raises:
        ValueError: If the protobuf payload contains an unsupported variant.

    Example:
        >>> value = deserialize_proto_Value(serialize_proto_Value(True))
        >>> value
        True
    """
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


def _proto_dtype_to_numpy_dtype(proto_dtype: hist_pb2.Dtype):
    """Mapping from hist_pb2.dtype messages to numpy dtypes."""
    match proto_dtype.type:
        case hist_pb2.Dtype.TYPE_DT_FLOAT32:
            return np.float32
        case hist_pb2.Dtype.TYPE_DT_FLOAT64:
            return np.float64
        case hist_pb2.Dtype.TYPE_DT_INT32:
            return np.int32
        case hist_pb2.Dtype.TYPE_DT_INT64:
            return np.int64
        case _:
            raise ValueError(f"Unsupported proto dtype: {proto_dtype.type}")


def serialize_hist(h: Hist) -> tuple[str, dict[str, hist_pb2.Value]]:
    """Serialize a histogram into metadata JSON and protobuf content fields.

    Args:
        h: Histogram to serialize.

    Returns:
        tuple[str, dict[str, hist_pb2.Value]]: JSON metadata and serialized
            storage payload keyed by storage field name.

    Example:
        >>> import hist
        >>> h = hist.Hist(hist.axis.Regular(4, 0, 1, name="x"))
        >>> metadata, contents = serialize_hist(h)
        >>> isinstance(metadata, str) and isinstance(contents, dict)
        True
    """
    # serialize
    hist_ser = hist.serialization.to_uhi(h)
    storage = hist_ser.pop("storage")
    # recover type
    hist_ser["storage"] = {"type": storage.pop("type")}
    # serialize all contents
    data_ser = {k: serialize_proto_Value(v) for k, v in storage.items()}
    return json.dumps(hist_ser, default=uhi.io.json.default), data_ser


def serialize_hist_storage(h: Hist) -> dict[str, hist_pb2.Value]:
    """Serialize only histogram storage arrays, excluding metadata."""
    hist_ser = hist.serialization.to_uhi(h)
    storage = hist_ser["storage"]
    storage.pop("type")
    return {key: serialize_proto_Value(value) for key, value in storage.items()}


def deserialize_hist_storage(
    template: Hist, contents: Mapping[str, hist_pb2.Value]
) -> Hist:
    """Reconstruct a histogram from a template and serialized storage arrays."""
    hist_json = hist.serialization.to_uhi(template)
    storage = hist_json["storage"]
    storage_type = storage["type"]
    hist_json["storage"] = {"type": storage_type}
    hist_json["storage"].update(
        {key: deserialize_proto_Value(value) for key, value in contents.items()}
    )
    return Hist(hist_json)


def deserialize_hist(metadata: str, contents: dict[str, hist_pb2.Value]) -> Hist:
    """Reconstruct a histogram from metadata JSON and serialized contents.

    Args:
        metadata: Histogram metadata JSON produced by `serialize_hist`.
        contents: Serialized storage payload produced by `serialize_hist`.

    Returns:
        Hist: Reconstructed histogram instance.

    Example:
        >>> import hist
        >>> h = hist.Hist(hist.axis.Regular(4, 0, 1, name="x"))
        >>> metadata, contents = serialize_hist(h)
        >>> restored = deserialize_hist(metadata, contents)
        >>> isinstance(restored, Hist)
        True
    """
    # load hist metadata (axes & storage type)
    hist_json = json.loads(metadata)
    # deserialize the content arrays from protobuf Value
    content = {k: deserialize_proto_Value(v) for k, v in contents.items()}
    # reconstruct the full hist json serialization
    hist_json["storage"].update(content)
    # instantiate a new hist
    return Hist(hist_json)


def serialize_unique_id(unique_id: tp.Any) -> bytes:
    """Serialize a `unique_id` into raw SHA256 digest bytes.

    Args:
        unique_id: JSON serializable object

    Returns:
        bytes: hashed version of `unique_id`.
    """
    return hashlib.sha256(
        json.dumps(unique_id, sort_keys=True).encode("utf-8")
    ).digest()

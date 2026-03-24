from __future__ import annotations

import json
import typing as tp

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

    # only compress array with more than 16 bytes
    if item.nbytes < 16:
        compressed_data = item.tobytes()
    else:
        compressed_data = codec.encode(item.tobytes())

    return hist_pb2.Ndarray(shape=shape, dtype=dtype, data=compressed_data)


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
            ndarray = message.array_value
            shape = tuple(ndarray.shape)
            dtype = _proto_dtype_to_numpy_dtype(ndarray.dtype)

            # we only compress arrays with more than 16 bytes
            if len(ndarray.data) < 16:
                decompressed_data = ndarray.data
            else:
                decompressed_data = codec.decode(ndarray.data)

            array = np.frombuffer(decompressed_data, dtype=dtype).reshape(shape)
            return array
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

from __future__ import annotations

import typing as tp

import numcodecs
import numpy as np

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
    item = np.ascontiguousarray(item)

    shape = list(item.shape)
    dtype = _numpy_dtype_to_proto_dtype(item.dtype)

    # only compress array with more than 16 bytes
    if item.nbytes < 16:
        compressed_data = item.tobytes()
    else:
        compressed_data = codec.encode(item.tobytes())

    return hist_pb2.Ndarray(shape=shape, dtype=dtype, data=compressed_data)


def serialize(item: tp.Any) -> hist_pb2.Value:
    """Serialize something into a hist_pb2.Value message."""
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


def deserialize(message: hist_pb2.Value):
    """Deserialize a hist_pb2.Value message into a numpy ndarray, str or int."""
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

from __future__ import annotations

import hashlib
import json
import typing as tp

import numpy as np
import numcodecs

from histserv.protos import hist_pb2

if tp.TYPE_CHECKING:
    from histserv.chunked_hist import ChunkKey, ChunkScalar, ChunkedHist


_ZSTD = numcodecs.Zstd(level=1)


def _encode_bytes(contents: bytes, codec: hist_pb2.CompressionCodec.ValueType) -> bytes:
    if codec == hist_pb2.COMPRESSION_CODEC_NONE:
        return contents
    if codec == hist_pb2.COMPRESSION_CODEC_ZSTD:
        return tp.cast(bytes, _ZSTD.encode(contents))
    raise ValueError(f"unsupported compression codec: {codec}")


def _decode_bytes(contents: bytes, codec: hist_pb2.CompressionCodec.ValueType) -> bytes:
    if codec == hist_pb2.COMPRESSION_CODEC_NONE:
        return contents
    if codec == hist_pb2.COMPRESSION_CODEC_ZSTD:
        return tp.cast(bytes, _ZSTD.decode(contents))
    raise ValueError(f"unsupported compression codec: {codec}")


def serialize_chunk_scalar(value: ChunkScalar) -> hist_pb2.ChunkScalar:
    if isinstance(value, str):
        return hist_pb2.ChunkScalar(string_value=value)
    return hist_pb2.ChunkScalar(int_value=value)


def deserialize_chunk_scalar(value: hist_pb2.ChunkScalar) -> ChunkScalar:
    which = value.WhichOneof("value")
    if which == "string_value":
        return value.string_value
    if which == "int_value":
        return value.int_value
    raise ValueError("chunk key value must be set")


def serialize_dense_view_bytes(
    dense_view: np.ndarray,
    *,
    shape: tuple[int, ...],
    dtype: np.dtype[tp.Any],
    codec: hist_pb2.CompressionCodec.ValueType = hist_pb2.COMPRESSION_CODEC_NONE,
) -> bytes:
    array = np.asarray(dense_view, order="C")
    if array.shape != shape:
        raise ValueError(
            f"dense view shape mismatch: expected {shape}, got {array.shape}"
        )
    if array.dtype != dtype:
        raise ValueError(
            f"dense view dtype mismatch: expected {dtype}, got {array.dtype}"
        )
    return _encode_bytes(array.tobytes(), codec)


def deserialize_dense_view_bytes(
    contents: bytes,
    *,
    shape: tuple[int, ...],
    dtype: np.dtype[tp.Any],
    expected_nbytes: int,
    codec: hist_pb2.CompressionCodec.ValueType = hist_pb2.COMPRESSION_CODEC_NONE,
) -> np.ndarray:
    decoded = _decode_bytes(contents, codec)
    if len(decoded) != expected_nbytes:
        raise ValueError(
            f"dense view byte size mismatch: expected {expected_nbytes}, got {len(decoded)}"
        )
    return np.frombuffer(decoded, dtype=dtype).reshape(shape)


def serialize_chunk_payload(
    key: ChunkKey,
    dense_view: np.ndarray,
    *,
    shape: tuple[int, ...],
    dtype: np.dtype[tp.Any],
    codec: hist_pb2.CompressionCodec.ValueType = hist_pb2.COMPRESSION_CODEC_NONE,
) -> hist_pb2.ChunkPayload:
    return hist_pb2.ChunkPayload(
        chunk_key=[serialize_chunk_scalar(value) for value in key],
        dense_view=serialize_dense_view_bytes(
            dense_view,
            shape=shape,
            dtype=dtype,
            codec=codec,
        ),
    )


def deserialize_chunk_key(
    contents: tp.Iterable[hist_pb2.ChunkScalar],
    *,
    axis_count: int,
) -> ChunkKey:
    values = tuple(deserialize_chunk_scalar(value) for value in contents)
    if len(values) != axis_count:
        raise ValueError("chunk payload keys do not match histogram chunk axes")
    return values


def serialize_chunked_hist_payload(
    chunked: ChunkedHist,
    *,
    codec: hist_pb2.CompressionCodec.ValueType = hist_pb2.COMPRESSION_CODEC_NONE,
) -> hist_pb2.ChunkedHistPayload:
    payload = hist_pb2.ChunkedHistPayload(
        hist_json=chunked.metadata_json(),
        dense_view_codec=codec,
    )
    for key, dense_view in chunked._chunks.items():
        payload.chunks.append(
            serialize_chunk_payload(
                key,
                dense_view,
                shape=chunked.dense_view_shape,
                dtype=chunked.dense_view_dtype,
                codec=codec,
            )
        )
    return payload


def merge_chunk_payloads(
    chunked: ChunkedHist,
    chunks: tp.Iterable[hist_pb2.ChunkPayload],
    *,
    codec: hist_pb2.CompressionCodec.ValueType = hist_pb2.COMPRESSION_CODEC_NONE,
) -> int:
    merged_bytes = 0
    for chunk in chunks:
        chunk_key = deserialize_chunk_key(
            chunk.chunk_key,
            axis_count=len(chunked.chunk_axis_names),
        )
        dense_view = deserialize_dense_view_bytes(
            chunk.dense_view,
            shape=chunked.dense_view_shape,
            dtype=chunked.dense_view_dtype,
            expected_nbytes=chunked._dense_view_nbytes,
            codec=codec,
        )
        merged_bytes += dense_view.nbytes
        chunked.add_dense_view(chunk_key, dense_view)
    return merged_bytes


def deserialize_chunked_hist_payload(
    payload: hist_pb2.ChunkedHistPayload,
) -> ChunkedHist:
    from histserv.chunked_hist import ChunkedHist

    chunked = ChunkedHist.from_metadata_json(payload.hist_json)
    merge_chunk_payloads(
        chunked,
        payload.chunks,
        codec=payload.dense_view_codec,
    )
    return chunked


def serialize_unique_id(unique_id: tp.Any) -> bytes:
    return hashlib.sha256(
        json.dumps(unique_id, sort_keys=True).encode("utf-8")
    ).digest()

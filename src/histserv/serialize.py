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
_LZ4 = numcodecs.LZ4(acceleration=1)
_CODECS = {
    "zstd": _ZSTD,
    "lz4": _LZ4,
}


def _normalize_codec(codec: str | None) -> str | None:
    if codec is None:
        return None
    if codec in _CODECS:
        return codec
    raise ValueError(f"unsupported compression codec: {codec!r}")


def _encode_bytes(contents: bytes, codec: str | None) -> bytes:
    codec = _normalize_codec(codec)
    if codec is None:
        return contents
    return tp.cast(bytes, _CODECS[codec].encode(contents))


def _decode_bytes(contents: bytes, codec: str | None) -> bytes:
    codec = _normalize_codec(codec)
    if codec is None:
        return contents
    return tp.cast(bytes, _CODECS[codec].decode(contents))


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
    codec: str | None = None,
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
    codec: str | None = None,
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
    codec: str | None = None,
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
    codec: str | None = None,
) -> hist_pb2.ChunkedHistPayload:
    payload = hist_pb2.ChunkedHistPayload(hist_json=chunked.metadata_json())
    normalized_codec = _normalize_codec(codec)
    if normalized_codec is not None:
        payload.dense_view_codec = normalized_codec
    for key, dense_view in chunked._chunks.items():
        payload.chunks.append(
            serialize_chunk_payload(
                key,
                dense_view,
                shape=chunked.dense_view_shape,
                dtype=chunked.dense_view_dtype,
                codec=normalized_codec,
            )
        )
    return payload


def merge_chunk_payloads(
    chunked: ChunkedHist,
    chunks: tp.Iterable[hist_pb2.ChunkPayload],
    *,
    codec: str | None = None,
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
        codec=payload.dense_view_codec
        if payload.HasField("dense_view_codec")
        else None,
    )
    return chunked


def serialize_unique_id(unique_id: tp.Any) -> bytes:
    return hashlib.sha256(
        json.dumps(unique_id, sort_keys=True).encode("utf-8")
    ).digest()

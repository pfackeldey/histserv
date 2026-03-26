from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import itertools
import typing as tp

import hist
import numpy as np

from histserv.util import reset_histogram

ChunkScalar = str | int
ChunkKey = tuple[ChunkScalar, ...]
DenseHist = hist.Hist

__all__ = [
    "ChunkKey",
    "ChunkScalar",
    "ChunkedHist",
    "DenseHist",
]


@dataclass(slots=True)
class ChunkAxisSpec:
    index: int
    name: str
    axis_type: type[hist.axis.IntCategory] | type[hist.axis.StrCategory]
    label: str
    metadata: tp.Any
    growth: bool
    flow: bool
    known_keys: list[ChunkScalar]


@dataclass(slots=True)
class ChunkedHist:
    """Single-threaded sparse chunked histogram for categorical axes."""

    chunk_axes: list[ChunkAxisSpec]
    full_template: DenseHist
    dense_template: DenseHist
    chunks: dict[ChunkKey, DenseHist] = field(default_factory=dict)

    @classmethod
    def from_hist(cls, source: hist.Hist) -> ChunkedHist:
        axes = list(source.axes)
        resolved = [
            (index, axis)
            for index, axis in enumerate(axes)
            if isinstance(axis, hist.axis.IntCategory | hist.axis.StrCategory)
        ]
        specs: list[ChunkAxisSpec] = []
        seen_indices: set[int] = set()
        for index, axis in resolved:
            if index in seen_indices:
                raise ValueError(f"duplicate chunk axis selection for index {index}")
            seen_indices.add(index)
            specs.append(
                ChunkAxisSpec(
                    index=index,
                    name=axis.name,
                    axis_type=type(axis),
                    label=axis.label,
                    metadata=axis.metadata,
                    growth=axis.traits.growth,
                    flow=axis.traits.overflow or axis.traits.underflow,
                    known_keys=[_normalize_chunk_scalar(key) for key in axis],
                )
            )

        dense_axes = [
            axis for index, axis in enumerate(axes) if index not in seen_indices
        ]
        full_template = reset_histogram(source)
        dense_template = hist.Hist(
            *dense_axes,
            storage=type(source.storage_type())(),
            name=source.name,
            label=source.label,
        )

        chunked = cls(
            chunk_axes=specs,
            full_template=full_template,
            dense_template=dense_template,
        )
        chunked._seed_known_chunks_from_hist(source)
        return chunked

    def _seed_known_chunks_from_hist(self, source: hist.Hist) -> None:
        if not self.chunk_axes:
            dense_chunk = self._new_dense_chunk()
            dense_chunk.view(flow=True)[...] = source.view(flow=True)
            self.chunks[()] = dense_chunk
            return

        if not any(spec.known_keys for spec in self.chunk_axes):
            return

        source_view = source.view(flow=True)
        for key_indices in itertools.product(
            *(range(len(spec.known_keys)) for spec in self.chunk_axes)
        ):
            dense_chunk = self._new_dense_chunk()
            selector: list[tp.Any] = [slice(None)] * source_view.ndim
            key_values: list[ChunkScalar] = []
            for spec, key_index in zip(self.chunk_axes, key_indices, strict=True):
                selector[spec.index] = key_index
                key_values.append(spec.known_keys[key_index])
            dense_chunk.view(flow=True)[...] = source_view[tuple(selector)]
            self.chunks[tuple(key_values)] = dense_chunk

    @property
    def chunk_axis_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.chunk_axes)

    def _new_dense_chunk(self) -> DenseHist:
        return hist.Hist(
            *self.dense_template.axes,
            storage=type(self.dense_template.storage_type())(),
            name=self.dense_template.name,
            label=self.dense_template.label,
        )

    def new_dense_hist(self) -> DenseHist:
        return self._new_dense_chunk()

    def _build_chunk_axis(
        self, spec: ChunkAxisSpec
    ) -> hist.axis.IntCategory | hist.axis.StrCategory:
        if spec.axis_type is hist.axis.IntCategory:
            return hist.axis.IntCategory(
                [tp.cast(int, key) for key in spec.known_keys],
                name=spec.name,
                label=spec.label,
                metadata=spec.metadata,
                growth=spec.growth,
                flow=spec.flow,
            )
        return hist.axis.StrCategory(
            [tp.cast(str, key) for key in spec.known_keys],
            name=spec.name,
            label=spec.label,
            metadata=spec.metadata,
            growth=spec.growth,
            flow=spec.flow,
        )

    def _require_chunk(self, key: ChunkKey) -> DenseHist:
        chunk = self.chunks.get(key)
        if chunk is None:
            chunk = self._new_dense_chunk()
            self.chunks[key] = chunk
            for spec, key_part in zip(self.chunk_axes, key, strict=True):
                if key_part not in spec.known_keys:
                    spec.known_keys.append(key_part)
        return chunk

    def split_fill_kwargs(
        self, kwargs: Mapping[str, tp.Any]
    ) -> tuple[ChunkKey, dict[str, tp.Any]]:
        missing = [name for name in self.chunk_axis_names if name not in kwargs]
        if missing:
            raise ValueError(f"missing chunk axes in fill kwargs: {missing!r}")

        scalar_keys: list[ChunkScalar] = []
        for name in self.chunk_axis_names:
            value = kwargs[name]
            if _is_scalar_like(value):
                scalar_keys.append(_normalize_chunk_scalar(value))
                continue
            raise ValueError(
                f"categorical chunk axis {name!r} only accepts scalar int/str values"
            )

        dense_kwargs = {
            name: value
            for name, value in kwargs.items()
            if name not in self.chunk_axis_names
        }
        return tuple(scalar_keys), dense_kwargs

    def add_dense_hist(self, key: ChunkKey, dense_hist: DenseHist) -> None:
        chunk = self._require_chunk(key)
        chunk_view = chunk.view(flow=True)
        dense_view = dense_hist.view(flow=True)
        if chunk_view.shape != dense_view.shape:
            raise ValueError(
                f"dense histogram shape mismatch: expected {chunk_view.shape}, got {dense_view.shape}"
            )
        chunk_view[...] += dense_view

    def _to_hist(self) -> hist.Hist:
        axes = list(self.full_template.axes)
        for spec in self.chunk_axes:
            axes[spec.index] = self._build_chunk_axis(spec)

        merged = hist.Hist(
            *axes,
            storage=type(self.full_template.storage_type())(),
            name=self.full_template.name,
            label=self.full_template.label,
        )

        merged_view = tp.cast(tp.Any, merged.view(flow=True))
        axis_key_to_index = [
            {key: index for index, key in enumerate(spec.known_keys)}
            for spec in self.chunk_axes
        ]

        for key, chunk in self.chunks.items():
            selector: list[tp.Any] = [slice(None)] * merged_view.ndim
            for spec, axis_map, key_part in zip(
                self.chunk_axes, axis_key_to_index, key, strict=True
            ):
                selector[spec.index] = axis_map[key_part]
            merged_view[tuple(selector)] = tp.cast(tp.Any, chunk.view(flow=True))
        return merged

    def to_hist(self) -> hist.Hist:
        return self._to_hist()

    def histogram_bytes(self) -> int:
        return sum(chunk.view(flow=True).nbytes for chunk in self.chunks.values())

    def keys(self) -> Iterable[ChunkKey]:
        return tuple(self.chunks)

    def __len__(self) -> int:
        return len(self.chunks)

    def __contains__(self, key: object) -> bool:
        return key in self.chunks

    def fill(self, **kwargs: tp.Any) -> None:
        chunk_key, dense_kwargs = self.split_fill_kwargs(kwargs)
        self._require_chunk(chunk_key).fill(**dense_kwargs)

    def reset(self) -> None:
        self.chunks.clear()
        for spec in self.chunk_axes:
            spec.known_keys.clear()


def _is_scalar_like(value: tp.Any) -> bool:
    if isinstance(value, str | bytes):
        return True
    if np.isscalar(value):
        return True
    if isinstance(value, np.ndarray) and value.ndim == 0:
        return True
    return False


def _normalize_chunk_scalar(value: tp.Any) -> ChunkScalar:
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, str | int):
        raise TypeError(
            f"chunk axis values must normalize to str or int, got {type(value)=}"
        )
    return value

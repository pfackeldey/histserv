from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import itertools
import typing as tp

import boost_histogram as bh
from boost_histogram.serialization._axis import _axis_from_dict, _axis_to_dict
from boost_histogram.serialization._common import serialize_metadata
from boost_histogram.serialization._storage import _storage_from_dict, _storage_to_dict
import hist
import numpy as np
import uhi.io.json

from histserv.util import bytes_repr

ChunkScalar = str | int
ChunkKey = tuple[ChunkScalar, ...]

__all__ = [
    "ChunkKey",
    "ChunkScalar",
    "ChunkedHist",
    "normalize_chunk_selection",
]


def _validate_supported_axis(axis: tp.Any) -> None:
    if (
        isinstance(axis, bh.axis.Regular)
        and getattr(axis, "transform", None) is not None
    ):
        raise ValueError("ChunkedHist does not support transformed Regular axes yet")


def _validate_supported_storage(storage: tp.Any) -> None:
    storage_type = type(storage)
    if storage_type in {bh.storage.Mean, bh.storage.WeightedMean}:
        raise ValueError(
            f"ChunkedHist does not support {storage_type.__name__} storage yet"
        )


def _validate_dense_view(
    view: tp.Any,
    *,
    shape: tuple[int, ...],
    dtype: np.dtype[tp.Any],
) -> np.ndarray:
    array = np.asarray(view)
    if array.shape != shape:
        raise ValueError(
            f"dense view shape mismatch: expected {shape}, got {array.shape}"
        )
    if array.dtype != dtype:
        raise ValueError(
            f"dense view dtype mismatch: expected {dtype}, got {array.dtype}"
        )
    return array


def _accumulate_dense_view(target: np.ndarray, source: np.ndarray) -> None:
    if target.dtype.fields is None:
        target[...] += source
        return
    for field_name in target.dtype.names or ():
        _accumulate_dense_view(target[field_name], source[field_name])


def _zero_dense_view(view: np.ndarray) -> None:
    if view.dtype.fields is None:
        view.fill(0)
        return
    for field_name in view.dtype.names or ():
        view[field_name].fill(0)


def _normalize_chunk_scalar(value: tp.Any) -> ChunkScalar:
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, str | int):
        raise TypeError(
            f"chunk axis values must normalize to str or int, got {type(value)=}"
        )
    return value


def _is_scalar_like(value: tp.Any) -> bool:
    if isinstance(value, str | bytes):
        return True
    if np.isscalar(value):
        return True
    if isinstance(value, np.ndarray) and value.ndim == 0:
        return True
    return False


def normalize_chunk_selection(
    selection: Mapping[str, ChunkScalar | tp.Iterable[ChunkScalar]],
    *,
    axis_names: Iterable[str],
    chunk_axis_names: Iterable[str],
) -> dict[str, tuple[ChunkScalar, ...]]:
    known_axes = set(axis_names)
    known_chunk_axes = set(chunk_axis_names)
    normalized: dict[str, tuple[ChunkScalar, ...]] = {}

    for axis_name, raw_value in selection.items():
        if axis_name not in known_axes:
            raise KeyError(f"unknown axis in slice: {axis_name!r}")
        if axis_name not in known_chunk_axes:
            raise ValueError(
                f"slicing only supports chunk axes; {axis_name!r} is dense"
            )
        if isinstance(raw_value, str | int):
            values = (raw_value,)
        else:
            values = tuple(raw_value)
        if not values:
            raise ValueError(f"slice for axis {axis_name!r} must be non-empty")
        normalized[axis_name] = tuple(
            _normalize_chunk_scalar(value) for value in values
        )

    return normalized


@dataclass(slots=True)
class ChunkAxisSpec:
    index: int
    name: str
    axis_type: type[tp.Any]
    label: str
    metadata: tp.Any
    growth: bool
    flow: bool
    known_keys: list[ChunkScalar]


@dataclass(slots=True, init=False)
class ChunkedHist:
    chunk_axes: list[ChunkAxisSpec]
    axes: tuple[tp.Any, ...]
    storage_type: type[tp.Any]
    name: str
    label: str
    _dense_view_shape: tuple[int, ...] = field(init=False)
    _dense_view_dtype: np.dtype[tp.Any] = field(init=False)
    _dense_view_nbytes: int = field(init=False)
    _chunk_axis_names: tuple[str, ...] = field(init=False)
    _scratch_dense_hist: hist.Hist = field(init=False)
    _chunks: dict[ChunkKey, np.ndarray] = field(default_factory=dict)

    def __init__(
        self,
        *axes: tp.Any,
        storage: tp.Any | None = None,
        name: str = "",
        label: str = "",
    ) -> None:
        """Initialize a chunked histogram.

        Args:
            *axes: Histogram axes. Named categorical axes become chunk axes.
            storage: Boost-histogram storage instance. Defaults to `Double()`.
            name: Histogram name.
            label: Histogram label.
        Example:
            >>> h = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> h.fill(x=[0.2, 0.4], cat="a")
        """
        if not axes:
            raise ValueError("ChunkedHist requires at least one axis")
        if not all(getattr(axis, "name", None) for axis in axes):
            raise ValueError("all axes must have names")
        if storage is None:
            storage = bh.storage.Double()
        for axis in axes:
            _validate_supported_axis(axis)
        _validate_supported_storage(storage)

        self.axes = tuple(axes)
        self.storage_type = type(storage)
        self.name = name
        self.label = label
        self._chunks = {}

        self.chunk_axes = []
        dense_axes: list[tp.Any] = []
        for index, axis in enumerate(self.axes):
            if isinstance(axis, bh.axis.IntCategory | bh.axis.StrCategory):
                self.chunk_axes.append(
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
            else:
                dense_axes.append(axis)

        self._chunk_axis_names = tuple(spec.name for spec in self.chunk_axes)

        self._scratch_dense_hist = hist.Hist(
            *dense_axes,
            storage=self.storage_type(),
            name=self.name,
            label=self.label,
        )
        dense_view = self._scratch_dense_hist.view(flow=True)
        self._dense_view_shape = dense_view.shape
        self._dense_view_dtype = dense_view.dtype
        self._dense_view_nbytes = dense_view.nbytes

    @classmethod
    def from_hist(
        cls,
        source: hist.Hist,
    ) -> ChunkedHist:
        """Build a `ChunkedHist` from an existing `hist.Hist`.

        Args:
            source: Source histogram to copy into chunked storage.
        Returns:
            A new `ChunkedHist` containing the same bin contents.

        Example:
            >>> source = hist.Hist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory(["a"], growth=True, name="cat"),
            ... )
            >>> source.fill(x=[0.2, 0.4], cat=["a", "a"])
            >>> chunked = ChunkedHist.from_hist(source)
        """
        chunked = cls(
            *source.axes,
            storage=type(source.storage_type())(),
            name=source.name or "",
            label=source.label or "",
        )
        source_view = source.view(flow=True)
        if not chunked.chunk_axes:
            chunked._save_chunk_view((), np.ascontiguousarray(source_view))
            return chunked

        if not any(spec.known_keys for spec in chunked.chunk_axes):
            return chunked

        for key_indices in itertools.product(
            *(range(len(spec.known_keys)) for spec in chunked.chunk_axes)
        ):
            selector: list[tp.Any] = [slice(None)] * source_view.ndim
            key_values: list[ChunkScalar] = []
            for spec, key_index in zip(chunked.chunk_axes, key_indices, strict=True):
                selector[spec.index] = key_index
                key_values.append(spec.known_keys[key_index])
            chunked._save_chunk_view(
                tuple(key_values),
                np.ascontiguousarray(source_view[tuple(selector)]),
            )

        return chunked

    @property
    def chunk_axis_names(self) -> tuple[str, ...]:
        return self._chunk_axis_names

    @property
    def dense_view_shape(self) -> tuple[int, ...]:
        return self._dense_view_shape

    @property
    def dense_view_dtype(self) -> np.dtype[tp.Any]:
        return self._dense_view_dtype

    @property
    def dense_axes(self) -> tuple[tp.Any, ...]:
        return tuple(self._scratch_dense_hist.axes)

    def _save_chunk_view(self, key: ChunkKey, chunk_view: np.ndarray) -> None:
        array = _validate_dense_view(
            np.ascontiguousarray(chunk_view),
            shape=self.dense_view_shape,
            dtype=self.dense_view_dtype,
        )
        if not array.flags.writeable:
            array = array.copy()
        self._chunks[key] = array

    def _remember_chunk_key(self, key: ChunkKey) -> None:
        for spec, key_part in zip(self.chunk_axes, key, strict=True):
            if key_part not in spec.known_keys:
                spec.known_keys.append(key_part)

    def split_fill_kwargs(
        self, kwargs: Mapping[str, tp.Any]
    ) -> tuple[ChunkKey, dict[str, tp.Any]]:
        missing = [name for name in self.chunk_axis_names if name not in kwargs]
        if missing:
            raise ValueError(f"missing chunk axes in fill kwargs: {missing!r}")

        chunk_key: list[ChunkScalar] = []
        for name in self.chunk_axis_names:
            value = kwargs[name]
            if not _is_scalar_like(value):
                raise ValueError(
                    f"categorical chunk axis {name!r} only accepts scalar int/str values"
                )
            chunk_key.append(_normalize_chunk_scalar(value))

        return tuple(chunk_key), {
            name: value
            for name, value in kwargs.items()
            if name not in self.chunk_axis_names
        }

    def add_dense_view(self, key: ChunkKey, dense_view: np.ndarray) -> None:
        dense_view = _validate_dense_view(
            dense_view,
            shape=self.dense_view_shape,
            dtype=self.dense_view_dtype,
        )
        chunk_view = self._chunks.get(key)
        if chunk_view is None:
            self._save_chunk_view(key, dense_view)
            self._remember_chunk_key(key)
            return
        _accumulate_dense_view(chunk_view, dense_view)

    def fill(self, **kwargs: tp.Any) -> None:
        """Fill one chunk of the histogram.

        Args:
            **kwargs: Named axis values and optional storage arguments such as
                `weight` or `sample`. Chunk axes must receive scalar values.

        Example:
            >>> h = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> h.fill(x=[0.2, 0.4], cat="a")
        """
        chunk_key, dense_kwargs = self.split_fill_kwargs(kwargs)
        dense_hist = self._scratch_dense_hist
        dense_view = dense_hist.view(flow=True)
        try:
            chunk_view = self._chunks.get(chunk_key)
            if chunk_view is not None:
                dense_view[...] = chunk_view
            dense_hist.fill(**dense_kwargs)
            existing = self._chunks.get(chunk_key)
            if existing is None:
                self._save_chunk_view(chunk_key, dense_view.copy(order="C"))
                self._remember_chunk_key(chunk_key)
            else:
                existing[...] = dense_view
        finally:
            _zero_dense_view(dense_view)

    def to_hist(self) -> hist.Hist:
        """Materialize the chunked histogram as a `hist.Hist`.

        Returns:
            A dense histogram with the currently known categorical keys.

        Example:
            >>> h = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> h.fill(x=[0.2, 0.4], cat="a")
            >>> dense = h.to_hist()
        """
        axes = list(self.axes)
        keys_by_axis = self._keys_by_axis(self._chunks)
        for spec in self.chunk_axes:
            keys = keys_by_axis[spec.name]
            if issubclass(spec.axis_type, bh.axis.IntCategory):
                axes[spec.index] = hist.axis.IntCategory(
                    [tp.cast(int, key) for key in keys],
                    name=spec.name,
                    label=spec.label,
                    metadata=spec.metadata,
                    growth=spec.growth,
                    flow=spec.flow,
                )
            else:
                axes[spec.index] = hist.axis.StrCategory(
                    [tp.cast(str, key) for key in keys],
                    name=spec.name,
                    label=spec.label,
                    metadata=spec.metadata,
                    growth=spec.growth,
                    flow=spec.flow,
                )

        merged = hist.Hist(
            *axes,
            storage=self.storage_type(),
            name=self.name,
            label=self.label,
        )
        merged_view = merged.view(flow=True)
        axis_key_to_index = [
            {key: index for index, key in enumerate(keys_by_axis[spec.name])}
            for spec in self.chunk_axes
        ]

        for key, chunk_view in self._chunks.items():
            selector: list[tp.Any] = [slice(None)] * merged_view.ndim
            for spec, axis_map, key_part in zip(
                self.chunk_axes, axis_key_to_index, key, strict=True
            ):
                selector[spec.index] = axis_map[key_part]
            merged_view[tuple(selector)] = chunk_view

        return merged

    def metadata_json(self) -> str:
        storage_schema = {
            key: value
            for key, value in _storage_to_dict(
                self.storage_type(),
                self._scratch_dense_hist.view(flow=True),
            ).items()
            if not isinstance(value, np.ndarray)
        }
        return json.dumps(
            {
                "uhi_schema": 1,
                "axes": [_axis_to_dict(axis) for axis in self.axes],
                "storage": storage_schema,
                "metadata": serialize_metadata(
                    {"name": self.name, "label": self.label}
                ),
            },
            default=uhi.io.json.default,
        )

    @classmethod
    def from_metadata_json(
        cls,
        metadata: str,
    ) -> ChunkedHist:
        payload = json.loads(metadata)
        axes = tuple(_axis_from_dict(axis_dict) for axis_dict in payload["axes"])
        storage = _storage_from_dict(payload["storage"])
        return cls(
            *axes,
            storage=storage,
            name=payload.get("metadata", {}).get("name", ""),
            label=payload.get("metadata", {}).get("label", ""),
        )

    def empty_like(self) -> ChunkedHist:
        return ChunkedHist(
            *self.axes,
            storage=self.storage_type(),
            name=self.name,
            label=self.label,
        )

    def items(self) -> Iterable[tuple[ChunkKey, np.ndarray]]:
        for key, chunk_view in self._chunks.items():
            yield key, np.ascontiguousarray(chunk_view)

    def _keys_by_axis(
        self,
        keys: Iterable[ChunkKey],
    ) -> dict[str, list[ChunkScalar]]:
        key_lists = {spec.name: [] for spec in self.chunk_axes}
        for key in keys:
            for spec, key_part in zip(self.chunk_axes, key, strict=True):
                key_lists[spec.name].append(key_part)
        return {
            axis_name: list(dict.fromkeys(values))
            for axis_name, values in key_lists.items()
        }

    def __getitem__(
        self,
        selection: Mapping[str, ChunkScalar | tp.Iterable[ChunkScalar]],
    ) -> ChunkedHist:
        """Select a subset of chunk keys.

        Args:
            selection: Mapping of chunk-axis name to one or more allowed values.

        Returns:
            A new `ChunkedHist` containing only matching chunks.

        Example:
            >>> h = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> h.fill(x=[0.2], cat="a")
            >>> h.fill(x=[0.4], cat="b")
            >>> only_a = h[{"cat": "a"}]
        """
        normalized = normalize_chunk_selection(
            selection,
            axis_names=(axis.name for axis in self.axes),
            chunk_axis_names=self.chunk_axis_names,
        )
        selected = {name: frozenset(values) for name, values in normalized.items()}
        matching_keys = [
            key
            for key in self._chunks
            if all(
                key_part in selected.get(spec.name, {key_part})
                for spec, key_part in zip(self.chunk_axes, key, strict=True)
            )
        ]

        result = self.empty_like()
        keys_by_axis = self._keys_by_axis(matching_keys)
        for result_spec in result.chunk_axes:
            result_spec.known_keys = keys_by_axis[result_spec.name]
        for key in matching_keys:
            result._save_chunk_view(key, self._chunks[key].copy(order="C"))
        return result

    def histogram_bytes(self) -> int:
        return sum(chunk.nbytes for chunk in self._chunks.values())

    def keys(self) -> Iterable[ChunkKey]:
        return self._chunks.keys()

    def __len__(self) -> int:
        return len(self._chunks)

    def __contains__(self, key: object) -> bool:
        return key in self._chunks

    def __repr__(self) -> str:
        axes_repr = ",\n  ".join(
            (
                f"{type(axis).__name__}(..., growth={axis.traits.growth}, "
                f"name={axis.name!r}, label={axis.label!r})"
            )
            if isinstance(axis, bh.axis.IntCategory | bh.axis.StrCategory)
            else repr(axis)
            for axis in self.axes
        )
        return (
            "ChunkedHist(\n"
            f"  {axes_repr},\n"
            f"  storage={self.storage_type()!r})"
            f" # Chunks: {len(self)}, Bytes: {bytes_repr(self.histogram_bytes())}"
        )

    def __iadd__(self, other: ChunkedHist | hist.Hist) -> ChunkedHist:
        """Merge another compatible histogram into this one in place.

        Args:
            other: Another `ChunkedHist` or `hist.Hist` with matching schema.

        Returns:
            This histogram after the merge.

        Example:
            >>> left = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> right = left.empty_like()
            >>> left.fill(x=[0.2], cat="a")
            >>> right.fill(x=[0.4], cat="a")
            >>> left += right
        """
        if isinstance(other, hist.Hist):
            other = ChunkedHist.from_hist(other)
        if not isinstance(other, ChunkedHist):
            return NotImplemented
        if (
            self.axes != other.axes
            or self.storage_type is not other.storage_type
            or self.name != other.name
            or self.label != other.label
        ):
            raise ValueError("cannot add incompatible histograms")
        for key, dense_view in other._chunks.items():
            self.add_dense_view(key, dense_view)
        return self

    def __add__(self, other: ChunkedHist | hist.Hist) -> ChunkedHist:
        """Return a merged copy of two compatible histograms.

        Args:
            other: Another `ChunkedHist` or `hist.Hist` with matching schema.

        Returns:
            A new `ChunkedHist` containing the merged contents.

        Example:
            >>> left = ChunkedHist(
            ...     hist.axis.Regular(10, 0, 1, name="x"),
            ...     hist.axis.StrCategory([], growth=True, name="cat"),
            ... )
            >>> right = left.empty_like()
            >>> left.fill(x=[0.2], cat="a")
            >>> right.fill(x=[0.4], cat="a")
            >>> merged = left + right
        """
        result = self.empty_like()
        result += self
        result += other
        return result

    def reset(self) -> None:
        self._chunks.clear()
        for spec in self.chunk_axes:
            spec.known_keys.clear()

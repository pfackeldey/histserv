from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import boost_histogram as bh
import hist
import numpy as np
from boost_histogram.serialization._axis import _axis_to_dict

from histserv.chunked_hist import ChunkAxisSpec, ChunkScalar
from histserv.service import HistogramEntry


def _chunk_axis_for_spec(spec: ChunkAxisSpec) -> object:
    if issubclass(spec.axis_type, bh.axis.IntCategory):
        return hist.axis.IntCategory(
            list(spec.known_keys),
            name=spec.name,
            label=spec.label,
            metadata=spec.metadata,
            growth=spec.growth,
            flow=spec.flow,
        )
    return hist.axis.StrCategory(
        list(spec.known_keys),
        name=spec.name,
        label=spec.label,
        metadata=spec.metadata,
        growth=spec.growth,
        flow=spec.flow,
    )


def _chunk_axis_type(spec: ChunkAxisSpec) -> str:
    return str(_axis_to_dict(_chunk_axis_for_spec(spec))["type"])


def _chunk_axis_payload(spec: ChunkAxisSpec) -> dict:
    return {
        "name": spec.name,
        "label": spec.label,
        "type": _chunk_axis_type(spec),
        "categories": list(spec.known_keys),
    }


def _chunk_axes_payload(entry: HistogramEntry) -> list[dict]:
    return [_chunk_axis_payload(spec) for spec in entry.hist.chunk_axes]


def _chunk_values(chunk_view: np.ndarray) -> list:
    if chunk_view.dtype.fields is None:
        return chunk_view.tolist()
    if "value" in chunk_view.dtype.fields:
        return chunk_view["value"].tolist()
    raise TypeError(
        f"unsupported structured dense view dtype without 'value' field: {chunk_view.dtype!r}"
    )


def histogram_metadata(hist_id: str, entry: HistogramEntry) -> dict:
    return {
        "hist_id": hist_id,
        "dense_metadata": entry.hist.dense_metadata_dict(),
        "chunk_axes": _chunk_axes_payload(entry),
    }


@dataclass(slots=True)
class _PlotJsonInputs:
    """Atomic snapshot captured on the event loop, safe to hand to a worker.

    `chunk_view` is an independent copy of the live chunk array, so the
    `.tolist()` conversion can run off-loop without racing concurrent gRPC
    mutations of the original.
    """

    hist_id: str
    exact_selection: dict[str, ChunkScalar]
    chunk_view: np.ndarray
    version: int


def capture_plot_json_inputs(
    hist_id: str,
    entry: HistogramEntry,
    *,
    selection: Mapping[str, ChunkScalar | Iterable[ChunkScalar]],
) -> _PlotJsonInputs:
    """Atomically copy the data needed to render one chunk to JSON.

    Must run synchronously on the event-loop thread (relative to mutating gRPC
    handlers) so the chunk lookup and copy cannot interleave with a fill. The
    returned snapshot owns its array and is safe to pass to `to_plot_json` in a
    worker thread.

    `selection` must identify exactly one chunk. For histograms without chunk
    axes this is the empty mapping.
    """
    chunk_key = entry.hist.exact_chunk_key(selection)
    exact_selection = entry.hist.selection_dict(chunk_key)
    chunk_view = entry.hist.chunk_view_copy(exact_selection)
    return _PlotJsonInputs(
        hist_id=hist_id,
        exact_selection=exact_selection,
        chunk_view=chunk_view,
        # ms-precision timestamp; changes whenever fills update last_access
        version=int(entry.last_access.timestamp() * 1000),
    )


def to_plot_json(inputs: _PlotJsonInputs) -> dict:
    """Convert a captured snapshot to a JSON-serializable dict.

    Touches only the owned copy in `inputs`, so it is safe to run in a worker
    thread (the expensive `.tolist()` happens here).
    """
    return {
        "hist_id": inputs.hist_id,
        "selection": inputs.exact_selection,
        "values": _chunk_values(inputs.chunk_view),
        "version": inputs.version,
    }


def histogram_to_plot_json(
    hist_id: str,
    entry: HistogramEntry,
    *,
    selection: Mapping[str, ChunkScalar | Iterable[ChunkScalar]],
) -> dict:
    """Materialize one selected dense chunk into a JSON-serializable dict.

    Convenience wrapper that captures and converts in one synchronous call.
    `selection` must identify exactly one chunk. For histograms without chunk
    axes this is the empty mapping.
    """
    return to_plot_json(
        capture_plot_json_inputs(hist_id, entry, selection=selection)
    )


def histogram_summary(hist_id: str, entry: HistogramEntry) -> dict:
    """Return lightweight dashboard metadata for hist_list messages."""
    return {
        "hist_id": hist_id,
        "name": entry.hist.name,
        "label": entry.hist.label,
        "chunk_axes": _chunk_axes_payload(entry),
        "bytes": entry.hist.histogram_bytes(),
        "last_access": entry.last_access.timestamp(),
        "token": entry.token,
    }

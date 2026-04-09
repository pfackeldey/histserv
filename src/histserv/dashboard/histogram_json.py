from __future__ import annotations

from collections.abc import Iterable, Mapping

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


def histogram_to_plot_json(
    hist_id: str,
    entry: HistogramEntry,
    *,
    selection: Mapping[str, ChunkScalar | Iterable[ChunkScalar]],
) -> dict:
    """Materialize one selected dense chunk into a JSON-serializable dict.

    `selection` must identify exactly one chunk. For histograms without chunk
    axes this is the empty mapping.
    """
    chunk_key = entry.hist.exact_chunk_key(selection)
    exact_selection = entry.hist.selection_dict(chunk_key)
    chunk_view = entry.hist.chunk_view(exact_selection)

    result: dict = {
        "hist_id": hist_id,
        "selection": exact_selection,
        "values": _chunk_values(chunk_view),
        # ms-precision timestamp; changes whenever fills update last_access
        "version": int(entry.last_access.timestamp() * 1000),
    }

    return result


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

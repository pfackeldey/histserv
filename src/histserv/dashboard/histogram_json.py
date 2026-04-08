from __future__ import annotations

import boost_histogram as bh
import numpy as np

from histserv.service import HistogramEntry


def _axis_info_full(axis: object) -> dict:
    """Extract axis metadata for hist_data messages (used when rendering)."""
    name = getattr(axis, "name", "")
    label = getattr(axis, "label", "") or name
    axis_type = type(axis).__name__

    if isinstance(axis, bh.axis.Boolean):
        return {
            "name": name,
            "label": label,
            "type": axis_type,
            "labels": ["False", "True"],
        }

    if isinstance(axis, bh.axis.IntCategory | bh.axis.StrCategory):
        return {
            "name": name,
            "label": label,
            "type": axis_type,
            "labels": [str(k) for k in axis],
        }

    # Continuous axes (Regular, Variable, Integer) all expose .edges
    edges: list[float] = axis.edges.tolist()  # type: ignore[union-attr]
    return {"name": name, "label": label, "type": axis_type, "edges": edges}


def _axis_info_summary(axis: object) -> dict:
    """Extract lightweight axis metadata for hist_list messages (no edges/values)."""
    name = getattr(axis, "name", "")
    axis_type = type(axis).__name__

    if isinstance(axis, bh.axis.Boolean):
        return {"name": name, "type": axis_type, "bins": 2}

    if isinstance(axis, bh.axis.IntCategory | bh.axis.StrCategory):
        return {"name": name, "type": axis_type, "categories": len(list(axis))}

    # Continuous: just report bin count and range
    edges: np.ndarray = axis.edges  # type: ignore[union-attr]
    return {
        "name": name,
        "type": axis_type,
        "bins": len(edges) - 1,
        "range": [float(edges[0]), float(edges[-1])],
    }


def histogram_to_plot_json(hist_id: str, entry: HistogramEntry) -> dict:
    """Materialize a HistogramEntry into a JSON-serializable dict for hist_data WS messages.

    Calls entry.hist.to_hist() which is CPU-bound; callers in async context should
    use asyncio.to_thread().
    """
    h = entry.hist.to_hist()

    values: list = h.values(flow=False).tolist()

    result: dict = {
        "hist_id": hist_id,
        "name": h.name or "",
        "label": h.label or "",
        "axes": [_axis_info_full(ax) for ax in h.axes],
        "values": values,
        "storage_type": type(h.storage_type()).__name__,
        # ms-precision timestamp; changes whenever fills update last_access
        "version": int(entry.last_access.timestamp() * 1000),
    }

    # For Weight storage, also expose variances so the frontend can show error bars
    if isinstance(h.storage_type(), bh.storage.Weight):
        variances = h.variances(flow=False)
        if variances is not None:
            result["variances"] = variances.tolist()

    return result


def histogram_summary(hist_id: str, entry: HistogramEntry) -> dict:
    """Return lightweight metadata for hist_list messages (no bin values)."""
    return {
        "hist_id": hist_id,
        "name": entry.hist.name,
        "label": entry.hist.label,
        "axes": [_axis_info_summary(ax) for ax in entry.hist.axes],
        "storage_type": entry.hist.storage_type.__name__,
        "bytes": entry.hist.histogram_bytes(),
        "last_access": entry.last_access.timestamp(),
        "token": entry.token,
    }

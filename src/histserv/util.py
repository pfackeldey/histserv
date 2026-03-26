from __future__ import annotations

from datetime import timedelta

import hist

__all__ = [
    "bytes_repr",
    "duration_repr",
    "reset_histogram",
    "timedelta_repr",
]


def bytes_repr(num_bytes: int) -> str:
    """Format a byte count using a compact human-readable unit.

    Args:
        num_bytes: Number of bytes to format.

    Returns:
        str: Human-readable string in bytes, KB, MB, or GB.

    Example:
        >>> bytes_repr(1536)
        '1.54 KB'
    """
    count, units = (
        (f"{num_bytes / 1e9:,.2f}", "GB")
        if num_bytes > 1e9
        else (f"{num_bytes / 1e6:,.2f}", "MB")
        if num_bytes > 1e6
        else (f"{num_bytes / 1e3:,.2f}", "KB")
        if num_bytes > 1e3
        else (f"{num_bytes:,}", "B")
    )

    return f"{count} {units}"


def duration_repr(num_seconds: float) -> str:
    """Format a duration using a compact human-readable unit.

    Args:
        num_seconds: Duration in seconds.

    Returns:
        str: Human-readable string in ns, us, ms, s, min, or h.

    Example:
        >>> duration_repr(0.0015)
        '1.50 ms'
    """
    count, units = (
        (f"{num_seconds / 3600:,.2f}", "h")
        if num_seconds >= 3600
        else (f"{num_seconds / 60:,.2f}", "min")
        if num_seconds >= 60
        else (f"{num_seconds:,.2f}", "s")
        if num_seconds >= 1
        else (f"{num_seconds * 1e3:,.2f}", "ms")
        if num_seconds >= 1e-3
        else (f"{num_seconds * 1e6:,.2f}", "us")
        if num_seconds >= 1e-6
        else (f"{num_seconds * 1e9:,.2f}", "ns")
    )

    return f"{count} {units}"


def timedelta_repr(delta: timedelta) -> str:
    """Format a ``timedelta`` using the same units as ``duration_repr``.

    Args:
        delta: Duration to format.

    Returns:
        str: Human-readable string in ns, us, ms, s, min, or h.

    Example:
        >>> timedelta_repr(timedelta(minutes=5))
        '5.00 min'
    """
    return duration_repr(delta.total_seconds())


def reset_histogram(source: hist.Hist) -> hist.Hist:
    """Return a fresh histogram with empty growable category axes."""
    axes = [_reset_axis(axis) for axis in source.axes]

    return hist.Hist(
        *axes,
        storage=type(source.storage_type())(),
        name=source.name,
        label=source.label,
    )


def _reset_axis(axis):
    if isinstance(axis, hist.axis.IntCategory):
        return hist.axis.IntCategory(
            [],
            name=axis.name,
            label=axis.label,
            metadata=axis.metadata,
            growth=True,
            flow=False,
        )
    if isinstance(axis, hist.axis.StrCategory):
        return hist.axis.StrCategory(
            [],
            name=axis.name,
            label=axis.label,
            metadata=axis.metadata,
            growth=True,
            flow=False,
        )
    return axis

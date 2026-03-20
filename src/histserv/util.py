from __future__ import annotations

__all__ = [
    "bytes_repr",
]


def bytes_repr(num_bytes: int) -> str:
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

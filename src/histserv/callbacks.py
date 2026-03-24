from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from histserv.logging import fmt_callback_logger_msg
from histserv.service import Histogrammer, logger
from histserv.util import bytes_repr


async def prune_old_hists(
    histogrammer: Histogrammer,
    delta: timedelta,
    interval: timedelta = timedelta(minutes=5),
) -> None:
    while True:
        now = datetime.now(timezone.utc)
        drop_ids = set()
        for hist_id, entry in histogrammer._entries.items():
            if (now - entry.last_access) >= delta:
                drop_ids.add(hist_id)

        for hist_id in drop_ids:
            logger.info(
                fmt_callback_logger_msg(
                    callback_method="prune_old_hists",
                    msg=(
                        f"dropping histogram ({hist_id}) because it hasn't "
                        f"been accessed since {delta}"
                    ),
                )
            )
            histogrammer._entries.pop(hist_id, None)

        await asyncio.sleep(interval.total_seconds())


async def print_hists_stats(
    histogrammer: Histogrammer,
    interval: timedelta = timedelta(seconds=5),
) -> None:
    while True:
        if histogrammer._entries:
            entries = list(histogrammer._entries.values())
            nhists = len(entries)

            logger.info(
                fmt_callback_logger_msg(
                    callback_method="print_hists_stats",
                    msg=(
                        f"using {bytes_repr(histogrammer._histogram_bytes(entries))} "
                        f"with {nhists} hists"
                    ),
                )
            )

        await asyncio.sleep(interval.total_seconds())

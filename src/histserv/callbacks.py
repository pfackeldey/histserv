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
        for hist_id in histogrammer.prune_entries_older_than(now=now, age=delta):
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
        entries = histogrammer.entries_snapshot()
        if entries:
            logger.info(
                fmt_callback_logger_msg(
                    callback_method="print_hists_stats",
                    msg=(
                        f"using {bytes_repr(histogrammer._histogram_bytes(list(entries)))} "
                        f"with {len(entries)} hists"
                    ),
                )
            )

        await asyncio.sleep(interval.total_seconds())

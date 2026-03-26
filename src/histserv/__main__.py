from __future__ import annotations

import asyncio
import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import timedelta

from histserv.logging import configure_logging, get_logger
from histserv.server import Server, ServerOptions
from histserv.util import timedelta_repr

logger = get_logger("histserv")


async def main() -> None:
    ap = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    ap.add_argument(
        "-p",
        "--port",
        default=0,
        type=int,
        help="TCP port to bind the gRPC server to.",
    )
    ap.add_argument(
        "--prune-after-seconds",
        default=24 * 60 * 60,
        type=float,
        help="Drop histograms that have not been accessed for at least this many seconds.",
    )
    ap.add_argument(
        "--prune-interval-seconds",
        default=60 * 5,
        type=float,
        help="How often to run the idle-histogram pruning callback, in seconds.",
    )
    ap.add_argument(
        "--stats-interval-seconds",
        default=5,
        type=float,
        help="How often to log aggregate histogram memory stats, in seconds.",
    )
    ap.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity.",
    )

    args = ap.parse_args()
    configure_logging(level=getattr(logging, args.log_level))

    options = ServerOptions(
        port=args.port,
        prune_after=timedelta(seconds=args.prune_after_seconds),
        prune_interval=timedelta(seconds=args.prune_interval_seconds),
        stats_interval=timedelta(seconds=args.stats_interval_seconds),
    )

    server = Server(options=options)
    await server.start()
    logger.info(
        "server (listening at %s) started with port=%s, "
        "prune_after=%s, prune_interval=%s, stats_interval=%s",
        server.address,
        options.port,
        timedelta_repr(options.prune_after),
        timedelta_repr(options.prune_interval),
        timedelta_repr(options.stats_interval),
    )
    try:
        await server.wait_for_termination()
    finally:
        logger.info("Starting graceful shutdown...")
        await server.stop(5)


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()

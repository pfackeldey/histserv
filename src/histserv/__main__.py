from __future__ import annotations

import asyncio
from argparse import ArgumentParser

from histserv.server import Server, logger

# Coroutines to be invoked when the event loop is shutting down.
_cleanup_coroutines = []


async def main() -> None:
    ap = ArgumentParser()
    ap.add_argument("-p", "--port", default=0, type=int)
    ap.add_argument("-t", "--n-threads", default=1, type=int)

    args = ap.parse_args()

    if not 0 <= args.port < 0xFFFF:
        raise ValueError("port must be between 0 and 65535")

    # start server
    server = Server(port=args.port, n_threads=args.n_threads)
    await server.start()

    async def server_graceful_shutdown():
        logger.info("Starting graceful shutdown...")
        # Shuts down the server with 5 seconds of grace period. During the
        # grace period, the server won't accept new connections and allow
        # existing RPCs to continue within the grace period.
        await server.stop(5)

    _cleanup_coroutines.append(server_graceful_shutdown())
    await server.wait_for_termination()


def run() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        if _cleanup_coroutines:
            loop.run_until_complete(*_cleanup_coroutines)
        loop.close()


if __name__ == "__main__":
    run()

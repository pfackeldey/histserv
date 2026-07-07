from __future__ import annotations

import asyncio

from histserv.server import Server, ServerOptions


def test_ephemeral_port_is_reported() -> None:
    async def run() -> None:
        server = Server(options=ServerOptions(port=0))
        await server.start()
        try:
            assert server.port != 0
            assert server.address == f"[::]:{server.port}"
        finally:
            await server.stop(grace=0)

    asyncio.run(run())


def test_explicit_port_is_kept() -> None:
    async def run() -> None:
        server = Server(options=ServerOptions(port=0))
        await server.start()
        try:
            # Grab the port the first server got, release it, and rebind
            # explicitly to show port/address reflect the requested port.
            port = server.port
        finally:
            await server.stop(grace=0)

        explicit = Server(options=ServerOptions(port=port))
        await explicit.start()
        try:
            assert explicit.port == port
            assert explicit.address == f"[::]:{port}"
        finally:
            await explicit.stop(grace=0)

    asyncio.run(run())

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Iterator

import pytest

from histserv.client import Client
from histserv.server import Server, ServerOptions


class GrpcServerThread:
    def __init__(self, port: int) -> None:
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Server | None = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._startup_error: BaseException | None = None

    @property
    def address(self) -> str:
        return f"localhost:{self.port}"

    def start(self, timeout: float = 5.0) -> None:
        self._thread.start()
        if not self._started.wait(timeout=timeout):
            raise RuntimeError("Timed out while starting the gRPC server")
        if self._startup_error is not None:
            raise RuntimeError(
                "Failed to start the gRPC server"
            ) from self._startup_error

    def stop(self, timeout: float = 5.0) -> None:
        if self._loop is None:
            return

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise RuntimeError("Timed out while stopping the gRPC server")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._start_server())
            self._started.set()
            loop.run_forever()
            loop.run_until_complete(self._stop_server())
        except BaseException as exc:  # pragma: no cover - fixture startup path
            self._startup_error = exc
            self._started.set()
        finally:
            loop.close()

    async def _start_server(self) -> None:
        self._server = Server(options=ServerOptions(port=self.port))
        await self._server.start()

    async def _stop_server(self) -> None:
        if self._server is None:
            return

        await self._server.stop(grace=0)


@pytest.fixture
def grpc_server() -> Iterator[GrpcServerThread]:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
        sock.bind(("::1", 0))
        port = sock.getsockname()[1]

    server = GrpcServerThread(port=port)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def client(grpc_server: GrpcServerThread) -> Iterator[Client]:
    with Client(grpc_server.address) as grpc_client:
        yield grpc_client

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

import grpc

from histserv.callbacks import print_hists_stats, prune_old_hists
from histserv.protos import hist_pb2_grpc
from histserv.service import Histogrammer, LoggingInterceptor


@dataclass(frozen=True)
class ServerOptions:
    port: int = 50051
    prune_after: timedelta = timedelta(days=1)
    prune_interval: timedelta = timedelta(minutes=5)
    stats_interval: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 0xFFFF:
            raise ValueError("port must be between 0 and 65535")
        if self.prune_after.total_seconds() < 0:
            raise ValueError("prune_after must be non-negative")
        if self.prune_interval.total_seconds() <= 0:
            raise ValueError("prune_interval must be positive")
        if self.stats_interval.total_seconds() <= 0:
            raise ValueError("stats_interval must be positive")


class Server:
    def __init__(
        self,
        *,
        options: ServerOptions,
    ) -> None:
        self.options = options
        self._started = False

        self.server = grpc.aio.server(
            interceptors=[LoggingInterceptor()],
            compression=grpc.Compression.NoCompression,
            options=[
                ("grpc.max_receive_message_length", 1 << 29),
            ],
        )

        self.histogrammer = Histogrammer()
        hist_pb2_grpc.add_HistogrammerServiceServicer_to_server(
            self.histogrammer, self.server
        )

        self._callbacks: list[asyncio.Task[None]] = []

        self.server.add_insecure_port(self.address)

    @property
    def address(self) -> str:
        return f"[::]:{self.options.port}"

    async def start(self) -> None:
        if self._started:
            return

        await self.server.start()
        self._callbacks = [
            asyncio.create_task(
                prune_old_hists(
                    histogrammer=self.histogrammer,
                    delta=self.options.prune_after,
                    interval=self.options.prune_interval,
                ),
                name="prune_old_hists",
            ),
            asyncio.create_task(
                print_hists_stats(
                    histogrammer=self.histogrammer,
                    interval=self.options.stats_interval,
                ),
                name="print_hists_stats",
            ),
        ]
        self._started = True

    async def stop(self, grace: float | None = None) -> None:
        if not self._started:
            return

        for task in self._callbacks:
            task.cancel()
        if self._callbacks:
            await asyncio.gather(*self._callbacks, return_exceptions=True)
            self._callbacks.clear()
        await self.server.stop(grace=grace)
        self._started = False

    async def wait_for_termination(self, timeout: float | None = None) -> None:
        await self.server.wait_for_termination(timeout=timeout)

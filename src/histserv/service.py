from __future__ import annotations

import json
import resource
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from collections.abc import Mapping
from typing import Final

import grpc
import hist
import uhi.io.json

from histserv import __version__
from histserv.chunked_hist import ChunkedHist
from histserv.logging import (
    fmt_rpc_logger_msg,
    fmt_rpc_logger_msg_no_hist_id,
    get_logger,
)
from histserv.protos import hist_pb2, hist_pb2_grpc
from histserv.serialize import (
    deserialize_hist_storage,
    deserialize_proto_Value,
    serialize_hist,
)
from histserv.util import bytes_repr, duration_repr

logger = get_logger("histserv")

RPC_INIT: Final = "Init"
RPC_DESCRIBE: Final = "Describe"
RPC_EXISTS: Final = "Exists"
RPC_FILL: Final = "Fill"
RPC_SNAPSHOT: Final = "Snapshot"
RPC_DELETE: Final = "Delete"
RPC_RESET: Final = "Reset"
RPC_FLUSH: Final = "Flush"
RPC_STATS: Final = "Stats"


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        rpc_method = handler_call_details.method.rsplit("/", 1)[-1]

        async def logging_wrapper(request, context):
            started = time.perf_counter()
            debug_enabled = logger.isEnabledFor(10)
            error_enabled = logger.isEnabledFor(40)
            request_size = request.ByteSize() if (debug_enabled or error_enabled) else 0

            try:
                response = await handler.unary_unary(request, context)
            except Exception:
                if error_enabled:
                    duration = time.perf_counter() - started
                    hist_id = getattr(request, "hist_id", None)
                    if isinstance(hist_id, str) and hist_id:
                        log_msg = fmt_rpc_logger_msg(
                            rpc_method=rpc_method,
                            hist_id=hist_id,
                            msg=(
                                f"request={bytes_repr(request_size)}, "
                                f"duration={duration_repr(duration)}, "
                                "response=<error>"
                            ),
                        )
                    else:
                        log_msg = fmt_rpc_logger_msg_no_hist_id(
                            rpc_method=rpc_method,
                            msg=(
                                f"request={bytes_repr(request_size)}, "
                                f"duration={duration_repr(duration)}, "
                                "response=<error>"
                            ),
                        )
                    logger.error(log_msg)
                raise

            if debug_enabled:
                response_size = response.ByteSize()
                duration = time.perf_counter() - started
                hist_id = getattr(request, "hist_id", None)
                if isinstance(hist_id, str) and hist_id:
                    log_msg = fmt_rpc_logger_msg(
                        rpc_method=rpc_method,
                        hist_id=hist_id,
                        msg=(
                            f"request={bytes_repr(request_size)}, "
                            f"response={bytes_repr(response_size)}, "
                            f"duration={duration_repr(duration)}"
                        ),
                    )
                else:
                    log_msg = fmt_rpc_logger_msg_no_hist_id(
                        rpc_method=rpc_method,
                        msg=(
                            f"request={bytes_repr(request_size)}, "
                            f"response={bytes_repr(response_size)}, "
                            f"duration={duration_repr(duration)}"
                        ),
                    )
                logger.debug(log_msg)
            return response

        return grpc.unary_unary_rpc_method_handler(
            logging_wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


@dataclass
class HistogramEntry:
    hist: ChunkedHist
    hist_json: str
    token: str | None
    last_access: datetime
    unique_ids: set[bytes]


@dataclass(frozen=True)
class TokenScopedStatsSnapshot:
    histogram_count: int
    histogram_bytes: int
    rpc_calls_total: dict[str, int]


@dataclass(frozen=True)
class StatsSnapshot:
    histogram_count: int
    histogram_bytes: int
    active_rpcs: int
    version: str
    uptime_seconds: int
    user_cpu_seconds: float
    system_cpu_seconds: float
    rpc_calls_total: dict[str, int]
    observed_at: datetime
    token_scoped: TokenScopedStatsSnapshot | None


class Histogrammer(hist_pb2_grpc.HistogrammerServiceServicer):
    def __init__(self) -> None:
        super().__init__()
        self._entries: dict[str, HistogramEntry] = {}
        self._active_rpcs = 0
        self._started_at = datetime.now(timezone.utc)
        self._rpc_calls_total: Counter[str] = Counter()
        self._rpc_calls_by_token: Counter[tuple[str, str]] = Counter()

    def _rpc_started(self, rpc_name: str, token: str | None) -> None:
        self._active_rpcs += 1
        self._rpc_calls_total[rpc_name] += 1
        if token is not None:
            self._rpc_calls_by_token[(token, rpc_name)] += 1

    def _rpc_finished(self) -> None:
        self._active_rpcs -= 1

    def _request_token(self, context: grpc.ServicerContext) -> str | None:
        for key, value in context.invocation_metadata():
            if key == "x-histserv-token":
                return value
        return None

    async def _abort_internal(
        self,
        *,
        context: grpc.ServicerContext,
        rpc_method: str,
        hist_id: str,
        exc: Exception,
    ) -> None:
        error_msg = f"unexpected server error during {rpc_method}: {exc!r}"
        logger.error(
            fmt_rpc_logger_msg(
                rpc_method=rpc_method,
                hist_id=hist_id,
                msg=error_msg,
            ),
            exc_info=exc,
        )
        await context.abort(grpc.StatusCode.INTERNAL, error_msg)

    def _get_entry(
        self,
        *,
        hist_id: str,
        request_token: str | None,
        touch: bool = True,
    ) -> HistogramEntry | None:
        entry = self._entries.get(hist_id)
        if entry is None:
            return None
        if entry.token is not None and entry.token != request_token:
            return None
        if touch:
            entry.last_access = datetime.now(timezone.utc)
        return entry

    async def _require_entry(
        self,
        *,
        context: grpc.ServicerContext,
        rpc_method: str,
        hist_id: str,
        request_token: str | None,
    ) -> HistogramEntry:
        entry = self._get_entry(hist_id=hist_id, request_token=request_token)
        if entry is not None:
            return entry

        error_msg = f"unknown histogram id: {hist_id}"
        logger.debug(
            fmt_rpc_logger_msg(
                rpc_method=rpc_method,
                hist_id=hist_id,
                msg=error_msg,
            )
        )
        await context.abort(grpc.StatusCode.NOT_FOUND, error_msg)
        raise AssertionError("unreachable")

    def _histogram_bytes(self, entries: list[HistogramEntry]) -> int:
        return sum(entry.hist.histogram_bytes() for entry in entries)

    @staticmethod
    def _materialize_hist(hist_obj: ChunkedHist) -> hist.Hist:
        return hist_obj.to_hist()

    def _deserialize_chunk_key(
        self, chunk_key_msg: Mapping[str, hist_pb2.Value]
    ) -> dict[str, object]:
        return {
            key: deserialize_proto_Value(value) for key, value in chunk_key_msg.items()
        }

    def _compute_stats(self, *, token: str | None) -> StatsSnapshot:
        entries = list(self._entries.values())
        rpc_calls_total = dict(self._rpc_calls_total)
        active_rpcs = self._active_rpcs
        started_at = self._started_at
        token_scoped = None

        if token is not None:
            token_entries = [
                entry for entry in self._entries.values() if entry.token == token
            ]
            token_scoped = TokenScopedStatsSnapshot(
                histogram_count=len(token_entries),
                histogram_bytes=self._histogram_bytes(token_entries),
                rpc_calls_total={
                    rpc_name: count
                    for (token_key, rpc_name), count in self._rpc_calls_by_token.items()
                    if token_key == token
                },
            )

        usage = resource.getrusage(resource.RUSAGE_SELF)
        observed_at = datetime.now(timezone.utc)
        uptime_seconds = int((observed_at - started_at).total_seconds())
        return StatsSnapshot(
            histogram_count=len(entries),
            histogram_bytes=self._histogram_bytes(entries),
            active_rpcs=active_rpcs,
            version=__version__,
            uptime_seconds=uptime_seconds,
            user_cpu_seconds=usage.ru_utime,
            system_cpu_seconds=usage.ru_stime,
            rpc_calls_total=rpc_calls_total,
            observed_at=observed_at,
            token_scoped=token_scoped,
        )

    def entries_snapshot(self) -> tuple[HistogramEntry, ...]:
        return tuple(self._entries.values())

    def prune_entries_older_than(self, *, now: datetime, age: timedelta) -> list[str]:
        removed: list[str] = []
        for hist_id, entry in tuple(self._entries.items()):
            if (now - entry.last_access) >= age:
                self._entries.pop(hist_id, None)
                removed.append(hist_id)
        return removed

    async def Init(
        self, request: hist_pb2.InitRequest, context: grpc.ServicerContext
    ) -> hist_pb2.InitResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_INIT, request_token)
        try:
            hist_id = uuid.uuid4().hex
            fmt_rpc_msg = partial(
                fmt_rpc_logger_msg, rpc_method=RPC_INIT, hist_id=hist_id
            )

            if hist_id in self._entries:
                error_msg = (
                    f"try again; init failed due to existing key (key={hist_id})."
                )
                logger.error(fmt_rpc_msg(msg=error_msg))
                await context.abort(grpc.StatusCode.INTERNAL, error_msg)

            try:
                source_hist = hist.Hist(
                    json.loads(request.hist_json, object_hook=uhi.io.json.object_hook)
                )
                hist_obj = ChunkedHist.from_hist(source_hist)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                error_msg = f"invalid init payload: {exc!r}"
                logger.error(fmt_rpc_msg(msg=error_msg))
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, error_msg)
            except grpc.RpcError:
                raise
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_INIT,
                    hist_id=hist_id,
                    exc=exc,
                )

            self._entries[hist_id] = HistogramEntry(
                hist=hist_obj,
                hist_json=request.hist_json,
                token=request_token,
                last_access=datetime.now(timezone.utc),
                unique_ids=set(),
            )

            logger.debug(fmt_rpc_msg(msg="initialized histogram"))
            return hist_pb2.InitResponse(hist_id=hist_id)
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Describe(
        self, request: hist_pb2.DescribeRequest, context: grpc.ServicerContext
    ) -> hist_pb2.DescribeResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_DESCRIBE, request_token)
        try:
            entry = await self._require_entry(
                context=context,
                rpc_method=RPC_DESCRIBE,
                hist_id=request.hist_id,
                request_token=request_token,
            )
            return hist_pb2.DescribeResponse(hist_json=entry.hist_json)
        finally:
            self._rpc_finished()

    async def Exists(
        self, request: hist_pb2.ExistsRequest, context: grpc.ServicerContext
    ) -> hist_pb2.ExistsResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_EXISTS, request_token)
        try:
            return hist_pb2.ExistsResponse(
                exists=self._get_entry(
                    hist_id=request.hist_id,
                    request_token=request_token,
                    touch=False,
                )
                is not None
            )
        finally:
            self._rpc_finished()

    async def Fill(
        self, request: hist_pb2.FillRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FillResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_FILL, request_token)
        try:
            hist_id = request.hist_id
            fmt_rpc_msg = partial(
                fmt_rpc_logger_msg, rpc_method=RPC_FILL, hist_id=hist_id
            )

            entry = await self._require_entry(
                context=context,
                rpc_method=RPC_FILL,
                hist_id=hist_id,
                request_token=request_token,
            )

            if request.HasField("unique_id") and request.unique_id in entry.unique_ids:
                error_msg = (
                    f"rejected fill of histogram id {hist_id}, because "
                    f"{request.unique_id=} already exists"
                )
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, error_msg)

            try:
                chunk_key_kwargs = self._deserialize_chunk_key(request.chunk_key)
                chunk_key, _ = entry.hist.split_fill_kwargs(chunk_key_kwargs)
                dense_hist = deserialize_hist_storage(
                    entry.hist.dense_template,
                    request.dense_storage,
                )
                entry.hist.add_dense_hist(chunk_key, dense_hist)
                if request.HasField("unique_id"):
                    entry.unique_ids.add(request.unique_id)

                logger.debug(
                    fmt_rpc_msg(
                        msg=(
                            "merged "
                            f"{bytes_repr(dense_hist.view(flow=True).nbytes)} "
                            "of prebinned storage"
                        )
                    )
                )
            except (TypeError, ValueError) as exc:
                error_msg = f"invalid fill request: {exc!r}"
                logger.error(fmt_rpc_msg(msg=error_msg))
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, error_msg)
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_FILL,
                    hist_id=hist_id,
                    exc=exc,
                )

            return hist_pb2.FillResponse()
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Snapshot(
        self, request: hist_pb2.SnapshotRequest, context: grpc.ServicerContext
    ) -> hist_pb2.SnapshotResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_SNAPSHOT, request_token)
        try:
            hist_id = request.hist_id
            try:
                entry = await self._require_entry(
                    context=context,
                    rpc_method=RPC_SNAPSHOT,
                    hist_id=hist_id,
                    request_token=request_token,
                )

                if request.delete_from_server:
                    hist_obj = self._entries.pop(hist_id).hist
                else:
                    hist_obj = entry.hist

                hist_json, data = serialize_hist(self._materialize_hist(hist_obj))

                logger.debug(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_SNAPSHOT,
                        hist_id=hist_id,
                        msg="created snapshot",
                    )
                )
                return hist_pb2.SnapshotResponse(hist_json=hist_json, data=data)
            except (TypeError, ValueError) as exc:
                error_msg = f"invalid snapshot state: {exc!r}"
                logger.error(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_SNAPSHOT,
                        hist_id=hist_id,
                        msg=error_msg,
                    )
                )
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, error_msg)
            except grpc.RpcError:
                raise
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_SNAPSHOT,
                    hist_id=hist_id,
                    exc=exc,
                )
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Delete(
        self, request: hist_pb2.DeleteRequest, context: grpc.ServicerContext
    ) -> hist_pb2.DeleteResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_DELETE, request_token)
        try:
            hist_id = request.hist_id
            try:
                await self._require_entry(
                    context=context,
                    rpc_method=RPC_DELETE,
                    hist_id=hist_id,
                    request_token=request_token,
                )
                self._entries.pop(hist_id, None)

                logger.debug(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_DELETE,
                        hist_id=hist_id,
                        msg="deleted histogram",
                    )
                )
                return hist_pb2.DeleteResponse()
            except grpc.RpcError:
                raise
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_DELETE,
                    hist_id=hist_id,
                    exc=exc,
                )
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Reset(
        self, request: hist_pb2.ResetRequest, context: grpc.ServicerContext
    ) -> hist_pb2.ResetResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_RESET, request_token)
        try:
            hist_id = request.hist_id
            entry = await self._require_entry(
                context=context,
                rpc_method=RPC_RESET,
                hist_id=hist_id,
                request_token=request_token,
            )

            try:
                entry.hist.reset()
                entry.unique_ids.clear()

                logger.debug(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_RESET,
                        hist_id=hist_id,
                        msg="reset histogram",
                    )
                )
                return hist_pb2.ResetResponse()
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_RESET,
                    hist_id=hist_id,
                    exc=exc,
                )
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Flush(
        self, request: hist_pb2.FlushRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FlushResponse:
        request_token = self._request_token(context)
        self._rpc_started(RPC_FLUSH, request_token)
        try:
            import h5py
            import uhi.io.hdf5

            hist_id = request.hist_id
            destination = request.destination

            if not destination.endswith((".h5", ".hdf5")):
                error_msg = (
                    f"invalid destination: {destination}, needs to be a hdf5 file, "
                    "e.g., 'hist.hdf5'"
                )
                logger.error(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_FLUSH,
                        hist_id=hist_id,
                        msg=error_msg,
                    )
                )
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, error_msg)

            try:
                entry = await self._require_entry(
                    context=context,
                    rpc_method=RPC_FLUSH,
                    hist_id=hist_id,
                    request_token=request_token,
                )
                hist_obj = self._materialize_hist(entry.hist)

                with h5py.File(destination, "w") as h5_file:
                    uhi.io.hdf5.write(h5_file.create_group(hist_id), hist_obj)

                self._entries.pop(hist_id, None)

                logger.debug(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_FLUSH,
                        hist_id=hist_id,
                        msg=f"flushed histogram to {destination}",
                    )
                )
                return hist_pb2.FlushResponse()
            except OSError as exc:
                error_msg = f"invalid flush destination: {exc!r}"
                logger.error(
                    fmt_rpc_logger_msg(
                        rpc_method=RPC_FLUSH,
                        hist_id=hist_id,
                        msg=error_msg,
                    )
                )
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, error_msg)
            except grpc.RpcError:
                raise
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_FLUSH,
                    hist_id=hist_id,
                    exc=exc,
                )
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

    async def Stats(
        self, request: hist_pb2.StatsRequest, context: grpc.ServicerContext
    ) -> hist_pb2.StatsResponse:
        del request
        request_token = self._request_token(context)
        self._rpc_started(RPC_STATS, request_token)
        try:
            if request_token is not None and not any(
                entry.token == request_token for entry in self._entries.values()
            ):
                error_msg = f"unknown token: {request_token}"
                logger.debug(
                    fmt_rpc_logger_msg_no_hist_id(
                        rpc_method=RPC_STATS,
                        msg=error_msg,
                    )
                )
                await context.abort(grpc.StatusCode.NOT_FOUND, error_msg)

            try:
                stats = self._compute_stats(token=request_token)
                token_scoped = None
                if stats.token_scoped is not None:
                    token_scoped = hist_pb2.TokenScopedStats(
                        histogram_count=stats.token_scoped.histogram_count,
                        histogram_bytes=stats.token_scoped.histogram_bytes,
                        rpc_calls_total=stats.token_scoped.rpc_calls_total,
                    )
                return hist_pb2.StatsResponse(
                    histogram_count=stats.histogram_count,
                    histogram_bytes=stats.histogram_bytes,
                    active_rpcs=stats.active_rpcs,
                    version=stats.version,
                    uptime_seconds=stats.uptime_seconds,
                    user_cpu_seconds=stats.user_cpu_seconds,
                    system_cpu_seconds=stats.system_cpu_seconds,
                    rpc_calls_total=stats.rpc_calls_total,
                    observed_at=stats.observed_at,
                    token_scoped=token_scoped,
                )
            except grpc.RpcError:
                raise
            except Exception as exc:
                await self._abort_internal(
                    context=context,
                    rpc_method=RPC_STATS,
                    hist_id="-",
                    exc=exc,
                )
        finally:
            self._rpc_finished()

        raise AssertionError("unreachable")

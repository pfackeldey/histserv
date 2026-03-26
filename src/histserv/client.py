from __future__ import annotations

import json
import typing as tp
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from typing import TypedDict

import grpc
import numpy as np
import uhi.io.json
import hist
from hist import Hist
from hist.axis import NamedAxesTuple

from histserv.chunked_hist import ChunkKey, ChunkScalar
from histserv.protos import hist_pb2, hist_pb2_grpc
from histserv.serialize import (
    deserialize_hist,
    serialize_hist_storage,
    serialize_proto_Value,
    serialize_unique_id,
)


class TokenScopedStatsDict(TypedDict):
    histogram_count: int
    histogram_bytes: int
    rpc_calls_total: dict[str, int]


class _StatsBaseDict(TypedDict):
    histogram_count: int
    histogram_bytes: int
    active_rpcs: int
    version: str
    uptime_seconds: int
    user_cpu_seconds: float
    system_cpu_seconds: float
    rpc_calls_total: dict[str, int]
    observed_at: datetime


class StatsDict(_StatsBaseDict, total=False):
    token_scoped: dict[str, TokenScopedStatsDict]


@dataclass(frozen=True, slots=True)
class FillPlan:
    chunk_axis_names: tuple[str, ...]
    dense_axes: tuple[tp.Any, ...]
    storage_type: type[tp.Any]
    name: str
    label: str

    @classmethod
    def from_hist(cls, hist_obj: Hist) -> FillPlan:
        chunk_axis_names = tuple(
            axis.name
            for axis in hist_obj.axes
            if isinstance(axis, hist.axis.IntCategory | hist.axis.StrCategory)
        )
        dense_axes = tuple(
            axis
            for axis in hist_obj.axes
            if not isinstance(axis, hist.axis.IntCategory | hist.axis.StrCategory)
        )
        return cls(
            chunk_axis_names=chunk_axis_names,
            dense_axes=dense_axes,
            storage_type=type(hist_obj.storage_type()),
            name=hist_obj.name or "",
            label=hist_obj.label or "",
        )

    def split_fill_kwargs(
        self, kwargs: Mapping[str, tp.Any]
    ) -> tuple[ChunkKey, dict[str, tp.Any]]:
        missing = [name for name in self.chunk_axis_names if name not in kwargs]
        if missing:
            raise ValueError(f"missing chunk axes in fill kwargs: {missing!r}")

        chunk_key: list[ChunkScalar] = []
        for name in self.chunk_axis_names:
            value = kwargs[name]
            if isinstance(value, np.generic):
                value = value.item()
            if not isinstance(value, str | int):
                raise ValueError(
                    f"categorical chunk axis {name!r} only accepts scalar int/str values"
                )
            chunk_key.append(value)

        dense_kwargs = {
            name: value
            for name, value in kwargs.items()
            if name not in self.chunk_axis_names
        }
        return tuple(chunk_key), dense_kwargs

    def make_dense_hist(self) -> Hist:
        return Hist(
            *self.dense_axes,
            storage=self.storage_type(),
            name=self.name,
            label=self.label,
        )


class Client:
    def __init__(self, address: str) -> None:
        self.address = address

    def __getstate__(self):
        state = dict(self.__dict__)
        state.pop("channel", None)
        state.pop("stub", None)
        return state

    def __enter__(self) -> Client:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback  # unused
        self.channel.close()

    @cached_property
    def channel(self) -> grpc.Channel:
        return grpc.insecure_channel(
            self.address,
            compression=grpc.Compression.NoCompression,  # turn off for now, we compress with numcodecs the byte buffer
            options=[
                ("grpc.max_send_message_length", 1 << 29),
            ],
        )

    @cached_property
    def stub(self) -> hist_pb2_grpc.HistogrammerServiceStub:
        return hist_pb2_grpc.HistogrammerServiceStub(self.channel)

    @staticmethod
    def _metadata(token: str | None) -> tuple[tuple[str, str], ...] | None:
        if token is None:
            return None
        return (("x-histserv-token", token),)

    def init(
        self, hist: Hist, *, token: str | None = None, timeout: int = 10
    ) -> RemoteHist:
        """Register a histogram on the server and return a remote handle.

        Args:
            hist: Histogram metadata used to initialize remote storage.
            token: Optional token used to scope ownership of the remote
                histogram.
            timeout: RPC timeout in seconds.

        Returns:
            RemoteHist: Handle for filling and retrieving the remote histogram.

        Raises:
            ValueError: If `hist` is not a `hist.Hist` or has unnamed axes.
            grpc.RpcError: If the server rejects initialization.

        Example:
            >>> import hist
            >>> h = hist.Hist(hist.axis.Regular(10, 0, 1, name="x"))
            >>> client = Client("localhost:50051")
            >>> remote = client.init(h, token="alice", timeout=5)
            >>> remote.fill(x=0.25, timeout=5)  # reuses token="alice"
        """
        if not isinstance(hist, Hist):
            raise ValueError(f"`hist` must of type `hist.Hist`, got {type(hist)=}")
        if not all(ax.name for ax in hist.axes):
            raise ValueError(
                "`hist` must have names for every axis, because `histserv` only supports filling with kwargs currently"
            )
        assert isinstance(hist.axes, NamedAxesTuple)

        # TODO: replace with metadata only serialization once this is resolved:
        # https://github.com/scikit-hep/boost-histogram/issues/1089
        json_obj = json.dumps(hist, default=uhi.io.json.default)
        request = hist_pb2.InitRequest(hist_json=json_obj)
        ret = self.stub.Init(
            request,
            timeout=timeout,
            metadata=self._metadata(token),
        )

        # create a remote hist that one can interact with
        return RemoteHist(
            client=self,
            hist_id=ret.hist_id,
            token=token,
            fill_plan=FillPlan.from_hist(hist),
        )

    def connect(self, hist_id: str, *, token: str | None = None) -> RemoteHist:
        """Create a handle for an already-existing remote histogram.

        This does not contact the server. It only reconstructs a `RemoteHist`
        from a known histogram id and optional token.

        Args:
            hist_id: Identifier of an existing remote histogram.
            token: Optional token required to access token-scoped histograms.

        Returns:
            RemoteHist: Handle for interacting with the existing remote
                histogram.

        Example:
            >>> client = Client("localhost:50051")
            >>> remote = client.connect("abc123", token="alice")
            >>> remote.snapshot(timeout=5)
        """
        return RemoteHist(
            client=self,
            hist_id=hist_id,
            token=token,
            fill_plan=None,
        )

    def stats(
        self,
        *,
        token: str | None = None,
        timeout: int = 10,
    ) -> StatsDict:
        """Fetch a point-in-time snapshot of server statistics.

        Args:
            token: Optional token used to extend the global stats with
                token-scoped counters and histogram data for that token.
            timeout: RPC timeout in seconds.

        Returns:
            dict: Parsed global server statistics. If a token is provided, the
                result also includes a `"token_scoped"` entry for that token.
                CPU counters always stay global process counters.

        Example:
            >>> client = Client("localhost:50051")
            >>> first = client.stats(token="alice", timeout=5)
            >>> second = client.stats(token="alice", timeout=5)
            >>> wall = (second["observed_at"] - first["observed_at"]).total_seconds()
            >>> cpu = (
            ...     (second["user_cpu_seconds"] + second["system_cpu_seconds"])
            ...     - (first["user_cpu_seconds"] + first["system_cpu_seconds"])
            ... )
            >>> fills = (
            ...     second["token_scoped"]["alice"]["rpc_calls_total"].get("Fill", 0)
            ...     - first["token_scoped"]["alice"]["rpc_calls_total"].get("Fill", 0)
            ... )
            >>> fills_per_cpu_second = fills / cpu if cpu > 0 else float("inf")
            >>> average_cpu_cores = cpu / wall if wall > 0 else 0.0
        """
        request = hist_pb2.StatsRequest()
        response = self.stub.Stats(
            request,
            timeout=timeout,
            metadata=self._metadata(token),
        )
        stats: StatsDict = {
            "histogram_count": response.histogram_count,
            "histogram_bytes": response.histogram_bytes,
            "active_rpcs": response.active_rpcs,
            "version": response.version,
            "uptime_seconds": response.uptime_seconds,
            "user_cpu_seconds": response.user_cpu_seconds,
            "system_cpu_seconds": response.system_cpu_seconds,
            "rpc_calls_total": dict(response.rpc_calls_total),
            "observed_at": response.observed_at.ToDatetime(),
        }
        if token is not None and response.HasField("token_scoped"):
            stats["token_scoped"] = {
                token: {
                    "histogram_count": response.token_scoped.histogram_count,
                    "histogram_bytes": response.token_scoped.histogram_bytes,
                    "rpc_calls_total": dict(response.token_scoped.rpc_calls_total),
                }
            }
        return stats


class RemoteHist:
    """Client-side handle for an existing remote histogram.

    Example:
        >>> client = Client("localhost:50051")
        >>> remote = client.connect("abc123", token="alice")
        >>> remote.snapshot(timeout=5)
    """

    __slots__ = ("_client", "_hist_id", "_token", "_fill_plan")

    def __init__(
        self,
        client: Client,
        hist_id: str,
        token: str | None = None,
        fill_plan: FillPlan | None = None,
    ) -> None:
        self._client = client
        self._hist_id = hist_id
        self._token = token
        self._fill_plan = fill_plan

    @property
    def client(self) -> Client:
        return self._client

    @property
    def hist_id(self) -> str:
        return self._hist_id

    @property
    def token(self) -> str | None:
        return self._token

    def _metadata(self) -> tuple[tuple[str, str], ...] | None:
        return self.client._metadata(self.token)

    def _require_fill_plan(self, *, timeout: int) -> FillPlan:
        if self._fill_plan is None:
            response = self.client.stub.Describe(
                hist_pb2.DescribeRequest(hist_id=self.hist_id),
                timeout=timeout,
                metadata=self._metadata(),
            )
            hist_obj = Hist(
                json.loads(response.hist_json, object_hook=uhi.io.json.object_hook)
            )
            self._fill_plan = FillPlan.from_hist(hist_obj)
        return self._fill_plan

    def __repr__(self) -> str:
        return (
            "RemoteHist("
            f"hist_id={self.hist_id!r}, "
            f"address={self.client.address!r}, "
            f"token={self.token!r}"
            ")"
        )

    def get_connection_info(self) -> dict[str, str | None]:
        """Return the information needed to reconnect to this remote histogram.

        The returned dictionary is suitable for passing back into
        ``Client.connect(...)``. It can also be serialized and stored between
        Python sessions.

        Returns:
            dict[str, str | None]: Connection information containing the
                remote histogram id and bound token.

        Example:
            >>> connection_info = remote.get_connection_info()
            >>> remote_reconnected = client.connect(**connection_info)

        Example:
            >>> import json
            >>> connection_info = remote.get_connection_info()
            >>> payload = json.dumps(connection_info)
            >>> restored = json.loads(payload)
            >>> remote_reconnected = client.connect(**restored)
        """
        return {
            "hist_id": self.hist_id,
            "token": self.token,
        }

    def fill(
        self, *, timeout: int = 10, unique_id: tp.Any | None = None, **kwargs: tp.Any
    ) -> hist_pb2.FillResponse:
        """Fill the remote histogram by forwarding keyword arguments directly.

        Args:
            timeout: RPC timeout in seconds.
            unique_id: if provided, any subsequent fill call with the same
                `unique_id` will be rejected by the server.
            **kwargs: Axis values and optional weights or samples accepted by
                `hist.Hist.fill`.

        Returns:
            hist_pb2.FillResponse: Empty response returned on success.

        Example:
            >>> response = remote.fill(x=0.25, timeout=5)
            >>> isinstance(response, hist_pb2.FillResponse)
            True
        """
        fill_plan = self._require_fill_plan(timeout=timeout)
        chunk_key, dense_kwargs = fill_plan.split_fill_kwargs(kwargs)
        dense_hist = fill_plan.make_dense_hist()
        dense_hist.fill(**dense_kwargs)

        request = hist_pb2.FillRequest(
            hist_id=self.hist_id,
            chunk_key={
                name: serialize_proto_Value(value)
                for name, value in zip(
                    fill_plan.chunk_axis_names, chunk_key, strict=True
                )
            },
            dense_storage=serialize_hist_storage(dense_hist),
        )
        if unique_id is not None:
            request.unique_id = serialize_unique_id(unique_id)
        return self.client.stub.Fill(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )

    def exists(self, *, timeout: int = 10) -> bool:
        """Check whether this remote histogram still exists on the server.

        Args:
            timeout: RPC timeout in seconds.

        Returns:
            bool: `True` if the histogram exists and is accessible.

        Example:
            >>> remote.exists(timeout=5)
            True
        """
        request = hist_pb2.ExistsRequest(hist_id=self.hist_id)
        response = self.client.stub.Exists(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )
        return response.exists

    def snapshot(
        self,
        delete_from_server: bool = False,
        *,
        timeout: int = 10,
    ) -> Hist:
        """Fetch the current histogram contents from the server.

        Args:
            delete_from_server: Whether to remove the histogram from the server
                after taking the snapshot.
            timeout: RPC timeout in seconds.

        Returns:
            Hist: Local histogram reconstructed from server data.

        Raises:
            grpc.RpcError: If the server rejects the snapshot request.

        Example:
            >>> hist_obj = remote.snapshot(timeout=5)
            >>> isinstance(hist_obj, Hist)
            True
        """
        request = hist_pb2.SnapshotRequest(
            hist_id=self.hist_id, delete_from_server=delete_from_server
        )
        ret = self.client.stub.Snapshot(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )

        return deserialize_hist(metadata=ret.hist_json, contents=ret.data)

    def flush(
        self,
        destination: str = "hist.h5",
        *,
        timeout: int = 10,
    ) -> hist_pb2.FlushResponse:
        """Flush the remote histogram to a destination handled by the server.
        ``.flush`` will always drop the histogram from the server.

        Args:
            destination: Output target interpreted by the server.
            timeout: RPC timeout in seconds.

        Returns:
            hist_pb2.FlushResponse: Empty response returned on success.

        Example:
            >>> response = remote.flush("output.h5", timeout=5)
            >>> isinstance(response, hist_pb2.FlushResponse)
            True
        """
        request = hist_pb2.FlushRequest(hist_id=self.hist_id, destination=destination)
        return self.client.stub.Flush(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )

    def delete(self, *, timeout: int = 10) -> hist_pb2.DeleteResponse:
        """Delete the remote histogram from the server.

        Args:
            timeout: RPC timeout in seconds.

        Returns:
            hist_pb2.DeleteResponse: Empty response returned on success.

        Example:
            >>> response = remote.delete(timeout=5)
            >>> isinstance(response, hist_pb2.DeleteResponse)
            True
        """
        request = hist_pb2.DeleteRequest(hist_id=self.hist_id)
        return self.client.stub.Delete(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )

    def reset(self, *, timeout: int = 10) -> hist_pb2.ResetResponse:
        """Reset the remote histogram on the server.

        Args:
            timeout: RPC timeout in seconds.

        Returns:
            hist_pb2.ResetResponse: Empty response returned on success.

        Example:
            >>> response = remote.reset(timeout=5)
            >>> isinstance(response, hist_pb2.ResetResponse)
            True
        """
        request = hist_pb2.ResetRequest(hist_id=self.hist_id)
        return self.client.stub.Reset(
            request,
            timeout=timeout,
            metadata=self._metadata(),
        )

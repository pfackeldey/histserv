from __future__ import annotations

import boost_histogram as bh
import grpc
import hist
import numpy as np
import pytest
from hist import Hist

from histserv.client import Client
from histserv.protos import hist_pb2


def _regular_hist() -> Hist:
    return hist.Hist(
        hist.axis.Regular(8, 0, 4, name="x"),
    )


def _weighted_categorical_hist() -> Hist:
    return hist.Hist(
        hist.axis.Regular(4, 0, 4, name="x"),
        hist.axis.IntCategory([], growth=True, name="cat"),
        storage=bh.storage.Weight(),
    )


def test_remote_fill_matches_local_hist_for_regular_axes(client: Client) -> None:
    local_hist = _regular_hist()
    remote_hist = client.init(_regular_hist(), token="alice")

    fill_calls = [
        {"x": np.array([0.25, 1.5, 3.75], dtype=np.float32)},
        {"x": np.array([0.5, 1.75], dtype=np.float32)},
    ]

    for fill_kwargs in fill_calls:
        local_hist.fill(**fill_kwargs)
        response = remote_hist.fill(**fill_kwargs)
        assert isinstance(response, hist_pb2.FillResponse)

    remote_snapshot = remote_hist.snapshot()
    np.testing.assert_equal(remote_snapshot.view(flow=True), local_hist.view(flow=True))


def test_remote_fill_reject_with_duped_unique_id(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")

    # first one succeeds
    remote_hist.fill(
        x=np.array([0.25, 1.5, 3.75], dtype=np.float32), unique_id=["foo", "bar"]
    )

    # second one errors
    with pytest.raises(grpc.RpcError, match="StatusCode.ALREADY_EXISTS"):
        remote_hist.fill(
            x=np.array([0.25, 1.5, 3.75], dtype=np.float32), unique_id=["foo", "bar"]
        )


def test_remote_fill_matches_local_hist_for_weighted_categorical_axes(
    client: Client,
) -> None:
    local_hist = _weighted_categorical_hist()
    remote_hist = client.init(_weighted_categorical_hist(), token="alice")

    fill_calls = [
        {
            "x": np.array([0.5, 1.5, 2.5], dtype=np.float64),
            "cat": np.array([1, 2, 1], dtype=np.int64),
            "weight": np.array([1.0, 2.0, 0.5], dtype=np.float64),
        },
        {
            "x": np.array([3.5, 0.5], dtype=np.float64),
            "cat": np.array([3, 2], dtype=np.int64),
            "weight": np.array([4.0, 1.5], dtype=np.float64),
        },
    ]

    for fill_kwargs in fill_calls:
        local_hist.fill(**fill_kwargs)
        response = remote_hist.fill(**fill_kwargs)
        assert isinstance(response, hist_pb2.FillResponse)

    remote_snapshot = remote_hist.snapshot()
    assert list(remote_snapshot.axes[1]) == list(local_hist.axes[1])
    np.testing.assert_equal(remote_snapshot.view(flow=True), local_hist.view(flow=True))


def test_snapshot_delete_from_server_removes_hist(client: Client) -> None:
    local_hist = _regular_hist()
    remote_hist = client.init(_regular_hist(), token="alice")

    fill_kwargs = {"x": np.array([0.5, 1.5], dtype=np.float32)}
    local_hist.fill(**fill_kwargs)

    response = remote_hist.fill(**fill_kwargs)
    assert isinstance(response, hist_pb2.FillResponse)

    dropped_snapshot = remote_hist.snapshot(delete_from_server=True)
    np.testing.assert_equal(
        dropped_snapshot.view(flow=True), local_hist.view(flow=True)
    )

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        remote_hist.snapshot()


def test_missing_hist_id_raises_not_found(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")
    remote_hist.snapshot(delete_from_server=True)

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        remote_hist.fill(x=np.array([0.5], dtype=np.float32))


def test_exists_reflects_presence_and_token_visibility(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")
    other_handle = client.connect(remote_hist.hist_id, token="bob")

    assert remote_hist.exists()
    assert not other_handle.exists()

    remote_hist.delete()

    assert not remote_hist.exists()
    assert not other_handle.exists()


def test_delete_removes_histogram(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")
    response = remote_hist.delete()

    assert isinstance(response, hist_pb2.DeleteResponse)
    assert not remote_hist.exists()

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        remote_hist.snapshot()


def test_get_connection_info_returns_reconnectable_payload(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")

    assert remote_hist.get_connection_info() == {
        "hist_id": remote_hist.hist_id,
        "token": "alice",
    }


def test_connect_round_trip_via_connection_info(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")
    connection_info = remote_hist.get_connection_info()
    reconnected = client.connect(**connection_info)

    remote_hist.fill(x=np.array([0.25, 1.5], dtype=np.float32))
    reconnected.fill(x=np.array([3.25], dtype=np.float32))

    expected = _regular_hist()
    expected.fill(x=np.array([0.25, 1.5], dtype=np.float32))
    expected.fill(x=np.array([3.25], dtype=np.float32))

    snapshot = reconnected.snapshot()
    np.testing.assert_equal(snapshot.view(flow=True), expected.view(flow=True))


def test_different_token_cannot_access_histogram(client: Client) -> None:
    remote_hist = client.init(_regular_hist(), token="alice")
    other_handle = client.connect(remote_hist.hist_id, token="bob")

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.fill(x=np.array([0.5], dtype=np.float32))

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.snapshot()

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.flush("other.h5")


def test_stats_support_global_and_token_scopes(client: Client) -> None:
    alice_hist = client.init(_regular_hist(), token="alice")
    bob_hist = client.init(_regular_hist(), token="bob")
    open_hist = client.init(_regular_hist())

    alice_hist.fill(x=np.array([0.25, 0.75], dtype=np.float32))
    bob_hist.fill(x=np.array([1.25], dtype=np.float32))
    open_hist.fill(x=np.array([2.25, 2.75, 3.25], dtype=np.float32))

    global_stats = client.stats()
    alice_stats = client.stats(token="alice")
    bob_stats = client.stats(token="bob")
    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        client.stats(token="nobody")

    assert global_stats["histogram_count"] == 3
    assert global_stats["histogram_bytes"] > 0
    assert global_stats["active_rpcs"] >= 1
    assert global_stats["version"]
    assert global_stats["uptime_seconds"] >= 0
    assert global_stats["user_cpu_seconds"] >= 0.0
    assert global_stats["system_cpu_seconds"] >= 0.0
    assert global_stats["rpc_calls_total"]["Fill"] == 3
    assert global_stats["rpc_calls_total"]["Init"] == 3
    assert "token_scoped" not in global_stats

    assert alice_stats["histogram_count"] == 3
    assert alice_stats["histogram_bytes"] > 0
    assert alice_stats["version"] == global_stats["version"]
    assert alice_stats["rpc_calls_total"]["Fill"] == 3
    assert alice_stats["rpc_calls_total"]["Init"] == 3
    assert alice_stats["token_scoped"]["alice"]["histogram_count"] == 1
    assert alice_stats["token_scoped"]["alice"]["histogram_bytes"] > 0
    assert alice_stats["token_scoped"]["alice"]["rpc_calls_total"]["Fill"] == 1
    assert alice_stats["token_scoped"]["alice"]["rpc_calls_total"]["Init"] == 1

    assert bob_stats["histogram_count"] == 3
    assert bob_stats["histogram_bytes"] > 0
    assert bob_stats["version"] == global_stats["version"]
    assert bob_stats["rpc_calls_total"]["Fill"] == 3
    assert bob_stats["rpc_calls_total"]["Init"] == 3
    assert bob_stats["token_scoped"]["bob"]["histogram_count"] == 1
    assert bob_stats["token_scoped"]["bob"]["histogram_bytes"] > 0
    assert bob_stats["token_scoped"]["bob"]["rpc_calls_total"]["Fill"] == 1
    assert bob_stats["token_scoped"]["bob"]["rpc_calls_total"]["Init"] == 1

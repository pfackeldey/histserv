from __future__ import annotations

import grpc
import numpy as np
import pytest
from hist import Hist

from histserv.client import Client
from histserv.protos import hist_pb2
from tests.histogram_fixtures import (
    CategoricalHistCase,
    categorical_hist_cases,
    regular_hist,
)

INTEGRATION_CATEGORICAL_CASES = categorical_hist_cases()[:2]


def _weighted_categorical_hist() -> Hist:
    return categorical_hist_cases()[0].make_hist()


def test_remote_fill_matches_local_hist_for_regular_axes(client: Client) -> None:
    local_hist = regular_hist()
    remote_hist = client.init(regular_hist(), token="alice")

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
    remote_hist = client.init(regular_hist(), token="alice")

    # first one succeeds
    remote_hist.fill(
        x=np.array([0.25, 1.5, 3.75], dtype=np.float32), unique_id=["foo", "bar"]
    )

    # second one errors
    with pytest.raises(grpc.RpcError, match="StatusCode.ALREADY_EXISTS"):
        remote_hist.fill(
            x=np.array([0.25, 1.5, 3.75], dtype=np.float32), unique_id=["foo", "bar"]
        )


@pytest.mark.parametrize(
    "case",
    INTEGRATION_CATEGORICAL_CASES,
    ids=lambda case: case.name,
)
def test_remote_fill_matches_local_hist_for_weighted_categorical_axes(
    client: Client,
    case: CategoricalHistCase,
) -> None:
    local_hist = case.make_hist()
    remote_hist = client.init(case.make_hist(), token="alice")

    for fill_kwargs in case.fill_calls:
        local_hist.fill(**fill_kwargs)
        response = remote_hist.fill(**fill_kwargs)
        assert isinstance(response, hist_pb2.FillResponse)

    remote_snapshot = remote_hist.snapshot()
    for axis_name, expected in zip(
        case.axis_names, case.expected_axis_values, strict=True
    ):
        axis_index = remote_snapshot.axes.name.index(axis_name)
        assert list(remote_snapshot.axes[axis_index]) == expected
    np.testing.assert_equal(remote_snapshot.view(flow=True), local_hist.view(flow=True))


def test_snapshot_delete_from_server_removes_hist(client: Client) -> None:
    local_hist = regular_hist()
    remote_hist = client.init(regular_hist(), token="alice")

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
    remote_hist = client.init(regular_hist(), token="alice")
    remote_hist.snapshot(delete_from_server=True)

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        remote_hist.fill(x=np.array([0.5], dtype=np.float32))


def test_exists_reflects_presence_and_token_visibility(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    other_handle = client.connect(remote_hist.hist_id, token="bob")

    assert remote_hist.exists()
    assert not other_handle.exists()

    remote_hist.delete()

    assert not remote_hist.exists()
    assert not other_handle.exists()


def test_delete_removes_histogram(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    response = remote_hist.delete()

    assert isinstance(response, hist_pb2.DeleteResponse)
    assert not remote_hist.exists()

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        remote_hist.snapshot()


@pytest.mark.parametrize(
    "case",
    INTEGRATION_CATEGORICAL_CASES,
    ids=lambda case: case.name,
)
def test_reset_clears_contents_and_collapses_growable_categories(
    client: Client,
    case: CategoricalHistCase,
) -> None:
    remote_hist = client.init(case.make_hist(), token="alice")

    first_fill = dict(case.fill_calls[0])
    second_fill = dict(case.fill_calls[1])
    remote_hist.fill(**first_fill, unique_id="fill-before-reset")
    remote_hist.fill(**second_fill)

    response = remote_hist.reset()
    assert isinstance(response, hist_pb2.ResetResponse)

    reset_snapshot = remote_hist.snapshot()
    expected_reset = case.make_hist()
    for axis_name in case.axis_names:
        axis_index = reset_snapshot.axes.name.index(axis_name)
        assert list(reset_snapshot.axes[axis_index]) == []
    np.testing.assert_equal(
        reset_snapshot.view(flow=True),
        expected_reset.view(flow=True),
    )

    refill_kwargs = dict(case.fill_calls[2])
    remote_hist.fill(**refill_kwargs, unique_id="fill-before-reset")
    remote_hist.fill(**case.fill_calls[3])

    expected_refilled = case.make_hist()
    expected_refilled.fill(**refill_kwargs)
    expected_refilled.fill(**case.fill_calls[3])
    refilled_snapshot = remote_hist.snapshot()
    for axis_name in case.axis_names:
        axis_index = refilled_snapshot.axes.name.index(axis_name)
        expected_axis_index = expected_refilled.axes.name.index(axis_name)
        assert list(refilled_snapshot.axes[axis_index]) == list(
            expected_refilled.axes[expected_axis_index]
        )
    np.testing.assert_equal(
        refilled_snapshot.view(flow=True),
        expected_refilled.view(flow=True),
    )


def test_remote_fill_rejects_array_values_for_int_categorical_axes(
    client: Client,
) -> None:
    remote_hist = client.init(_weighted_categorical_hist(), token="alice")
    invalid_fill = {
        "x": np.array([0.5, 1.5], dtype=np.float64),
        "cat": np.array([1, 1], dtype=np.int64),
        "weight": np.array([1.0, 2.0], dtype=np.float64),
    }

    with pytest.raises(
        ValueError,
        match=r"categorical chunk axis 'cat' only accepts scalar int/str values",
    ):
        remote_hist.fill(**invalid_fill)


def test_get_connection_info_returns_reconnectable_payload(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")

    assert remote_hist.get_connection_info() == {
        "hist_id": remote_hist.hist_id,
        "token": "alice",
    }


def test_connect_round_trip_via_connection_info(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    connection_info = remote_hist.get_connection_info()
    reconnected = client.connect(**connection_info)

    remote_hist.fill(x=np.array([0.25, 1.5], dtype=np.float32))
    reconnected.fill(x=np.array([3.25], dtype=np.float32))

    expected = regular_hist()
    expected.fill(x=np.array([0.25, 1.5], dtype=np.float32))
    expected.fill(x=np.array([3.25], dtype=np.float32))

    snapshot = reconnected.snapshot()
    np.testing.assert_equal(snapshot.view(flow=True), expected.view(flow=True))


def test_different_token_cannot_access_histogram(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    other_handle = client.connect(remote_hist.hist_id, token="bob")

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.fill(x=np.array([0.5], dtype=np.float32))

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.snapshot()

    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        other_handle.flush("other.h5")


def test_stats_support_global_and_token_scopes(client: Client) -> None:
    alice_hist = client.init(regular_hist(), token="alice")
    bob_hist = client.init(regular_hist(), token="bob")
    open_hist = client.init(regular_hist())

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

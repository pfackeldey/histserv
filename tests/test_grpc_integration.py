from __future__ import annotations

import grpc
import numpy as np
import pytest
from hist import Hist

from histserv.chunked_hist import ChunkedHist
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
    np.testing.assert_equal(
        remote_snapshot.to_hist().view(flow=True), local_hist.view(flow=True)
    )


def test_remote_fill_many_matches_local_hist_for_regular_axes(client: Client) -> None:
    local_hist = regular_hist()
    remote_hist = client.init(regular_hist(), token="alice")

    fill_calls = [
        {"x": np.array([0.25, 1.5, 3.75], dtype=np.float32)},
        {"x": np.array([0.5, 1.75], dtype=np.float32)},
    ]
    for fill_kwargs in fill_calls:
        local_hist.fill(**fill_kwargs)

    response = remote_hist.fill_many(fill_calls)
    assert isinstance(response, hist_pb2.FillResponse)

    remote_snapshot = remote_hist.snapshot()
    np.testing.assert_equal(
        remote_snapshot.to_hist().view(flow=True), local_hist.view(flow=True)
    )


def test_init_preserves_existing_bin_yields(client: Client) -> None:
    local = regular_hist()
    local.fill(x=np.array([0.25, 1.5, 3.75], dtype=np.float32))
    remote_hist = client.init(local, token="alice")
    np.testing.assert_equal(
        remote_hist.snapshot().to_hist().view(flow=True), local.view(flow=True)
    )


def test_remote_fill_reject_with_duped_unique_id(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    remote_hist.fill(
        x=np.array([0.25, 1.5, 3.75], dtype=np.float32), unique_id=["foo", "bar"]
    )
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

    remote_snapshot = remote_hist.snapshot().to_hist()
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
    remote_hist.fill(**fill_kwargs)

    dropped_snapshot = remote_hist.snapshot(delete_from_server=True)
    np.testing.assert_equal(
        dropped_snapshot.to_hist().view(flow=True), local_hist.view(flow=True)
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
    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        client.connect(remote_hist.hist_id, token="bob")

    assert remote_hist.exists()

    remote_hist.delete()

    assert not remote_hist.exists()


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

    reset_snapshot = remote_hist.snapshot().to_hist()
    expected_reset = case.make_hist()
    for axis_name in case.axis_names:
        axis_index = reset_snapshot.axes.name.index(axis_name)
        assert list(reset_snapshot.axes[axis_index]) == []
    np.testing.assert_equal(
        reset_snapshot.view(flow=True), expected_reset.view(flow=True)
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
    np.testing.assert_equal(
        snapshot.to_hist().view(flow=True), expected.view(flow=True)
    )


def test_different_token_cannot_access_histogram(client: Client) -> None:
    remote_hist = client.init(regular_hist(), token="alice")
    with pytest.raises(grpc.RpcError, match="StatusCode.NOT_FOUND"):
        client.connect(remote_hist.hist_id, token="bob")


def test_remote_slice_snapshot_returns_only_selected_chunks(client: Client) -> None:
    remote_hist = client.init(
        Hist.new.Reg(4, 0, 4, name="x")
        .IntCat([], growth=True, name="cat")
        .StrCat([], growth=True, name="var")
        .Weight()
    )
    remote_hist.fill(
        x=np.array([0.5], dtype=np.float32),
        cat=1,
        var="a",
        weight=np.array([1.0], dtype=np.float32),
    )
    remote_hist.fill(
        x=np.array([1.5], dtype=np.float32),
        cat=1,
        var="b",
        weight=np.array([1.0], dtype=np.float32),
    )
    remote_hist.fill(
        x=np.array([2.5], dtype=np.float32),
        cat=2,
        var="a",
        weight=np.array([1.0], dtype=np.float32),
    )

    sliced = remote_hist[{"cat": 1}].snapshot().to_hist()

    assert list(sliced.axes["cat"]) == [1]
    np.testing.assert_equal(sliced.sum(flow=True).value, 2.0)

from __future__ import annotations

import boost_histogram as bh
import hist
import numpy as np
import pytest

from histserv.chunked_hist import ChunkedHist
from tests.histogram_fixtures import CategoricalHistCase, categorical_hist_cases


def _weighted_categorical_hist() -> hist.Hist:
    return hist.Hist(
        hist.axis.Regular(4, 0, 4, name="x"),
        hist.axis.IntCategory([], growth=True, name="cat"),
        storage=bh.storage.Weight(),
    )


@pytest.mark.parametrize(
    "case",
    categorical_hist_cases(),
    ids=lambda case: case.name,
)
def test_chunked_hist_matches_regular_hist_for_vectorized_fill(
    case: CategoricalHistCase,
) -> None:
    regular = case.make_hist()
    chunked = ChunkedHist.from_hist(case.make_hist())

    for fill_kwargs in case.fill_calls:
        regular.fill(**fill_kwargs)
        chunked.fill(**fill_kwargs)

    restored = chunked.to_hist()
    for axis_name, expected in zip(
        case.axis_names, case.expected_axis_values, strict=True
    ):
        axis_index = restored.axes.name.index(axis_name)
        assert list(restored.axes[axis_index]) == expected
    np.testing.assert_equal(restored.view(flow=True), regular.view(flow=True))
    first_key = tuple(case.fill_calls[0][axis_name] for axis_name in case.axis_names)
    assert first_key in chunked


def test_chunked_hist_preserves_existing_contents_when_created_from_hist() -> None:
    source = _weighted_categorical_hist()
    source.fill(
        x=np.array([0.5, 1.5, 0.5], dtype=np.float64),
        cat=np.array([7, 8, 7], dtype=np.int64),
        weight=np.array([1.0, 2.0, 3.0], dtype=np.float64),
    )

    chunked = ChunkedHist.from_hist(source)
    restored = chunked.to_hist()

    assert list(restored.axes[1]) == [7, 8]
    np.testing.assert_equal(restored.view(flow=True), source.view(flow=True))


def test_chunked_hist_can_wrap_regular_hist_without_categorical_axes() -> None:
    source = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
    source.fill(x=np.array([0.5, 1.5], dtype=np.float64))

    chunked = ChunkedHist.from_hist(source)
    restored = chunked.to_hist()

    np.testing.assert_equal(restored.view(flow=True), source.view(flow=True))
    assert () in chunked


def test_chunked_hist_precreates_known_category_chunks() -> None:
    source = hist.Hist(
        hist.axis.Regular(4, 0, 4, name="x"),
        hist.axis.IntCategory([1, 2], growth=True, name="cat"),
        hist.axis.StrCategory(["a", "b"], growth=True, name="label"),
        storage=bh.storage.Weight(),
    )

    chunked = ChunkedHist.from_hist(source)

    assert (1, "a") in chunked
    assert (1, "b") in chunked
    assert (2, "a") in chunked
    assert (2, "b") in chunked
    assert len(list(chunked.keys())) == 4


def test_chunked_hist_can_chunk_multiple_categorical_axes() -> None:
    source = hist.Hist(
        hist.axis.Regular(4, 0, 4, name="x"),
        hist.axis.IntCategory([], growth=True, name="cat"),
        hist.axis.StrCategory([], growth=True, name="label"),
        storage=bh.storage.Weight(),
    )
    source.fill(
        x=np.array([0.5, 1.5, 2.5], dtype=np.float64),
        cat=np.array([1, 1, 2], dtype=np.int64),
        label=np.array(["a", "b", "a"]),
        weight=np.array([1.0, 2.0, 3.0], dtype=np.float64),
    )

    chunked = ChunkedHist.from_hist(source)
    restored = chunked.to_hist()

    assert (1, "a") in chunked
    assert (1, "b") in chunked
    assert (2, "a") in chunked
    assert list(restored.axes[1]) == [1, 2]
    assert list(restored.axes[2]) == ["a", "b"]
    np.testing.assert_equal(restored.view(flow=True), source.view(flow=True))


@pytest.mark.parametrize(
    "case",
    categorical_hist_cases(),
    ids=lambda case: case.name,
)
def test_chunked_hist_rejects_array_values_for_categorical_axes(
    case: CategoricalHistCase,
) -> None:
    chunked = ChunkedHist.from_hist(case.make_hist())
    invalid_fill = dict(case.fill_calls[0])
    axis_name = case.axis_names[0]
    axis_value = invalid_fill[axis_name]
    dtype = np.int64 if isinstance(axis_value, int) else np.str_
    invalid_fill[axis_name] = np.array([axis_value, axis_value], dtype=dtype)

    with pytest.raises(
        ValueError,
        match=rf"categorical chunk axis '{axis_name}' only accepts scalar int/str values",
    ):
        chunked.fill(**invalid_fill)

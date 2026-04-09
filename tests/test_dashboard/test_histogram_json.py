from __future__ import annotations

from datetime import datetime, timezone

import boost_histogram as bh
import hist
import pytest

from histserv.chunked_hist import ChunkedHist
from histserv.dashboard.histogram_json import (
    histogram_metadata,
    histogram_summary,
    histogram_to_plot_json,
)
from histserv.service import HistogramEntry


def _make_entry(h: hist.Hist) -> tuple[str, HistogramEntry]:
    chunked = ChunkedHist.from_hist(h)
    entry = HistogramEntry(
        hist=chunked,
        token=None,
        last_access=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        unique_ids=set(),
    )
    return "abc123", entry


class TestHistogramToPlotJson:
    def test_regular_axis_edges(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x", label="x-axis"))
        h.fill(x=[0.5, 1.5, 2.5])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        assert result["hist_id"] == hist_id
        assert result["selection"] == {}
        assert len(result["values"]) == 6
        assert result["values"][2] == pytest.approx(1.0)

    def test_variable_axis_edges(self) -> None:
        edges = [0.0, 1.0, 3.0, 6.0]
        h = hist.Hist(hist.axis.Variable(edges, name="pt", label="p_{T}"))
        h.fill(pt=[0.5, 2.0, 4.0])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        assert len(result["values"]) == 5
        assert result["values"][2] == pytest.approx(1.0)

    def test_str_category_labels(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b", "c"], name="cat", label="category"),
        )
        h.fill(x=[0.5, 1.5, 2.5], cat=["a", "b", "c"])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={"cat": "b"})

        assert result["selection"] == {"cat": "b"}
        assert len(result["values"]) == 6
        assert result["values"][2] == pytest.approx(1.0)

    def test_int_category_labels(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.IntCategory([10, 20, 30], name="run", label="run number"),
        )
        h.fill(x=[0.5, 1.5, 2.5], run=[10, 20, 30])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={"run": 20})

        assert result["selection"] == {"run": 20}
        assert len(result["values"]) == 6

    @pytest.mark.parametrize(
        ("storage", "fill_kwargs", "expected_values"),
        [
            (bh.storage.Double(), {}, [0.0, 1.0, 1.0, 0.0]),
            (bh.storage.Int64(), {}, [0, 1, 1, 0]),
            (bh.storage.AtomicInt64(), {}, [0, 1, 1, 0]),
            (bh.storage.Unlimited(), {}, [0.0, 1.0, 1.0, 0.0]),
            (bh.storage.Weight(), {"weight": [2.0, 3.0]}, [0.0, 2.0, 3.0, 0.0]),
        ],
        ids=["double", "int64", "atomic_int64", "unlimited", "weight"],
    )
    def test_supported_storage_types_emit_values_only(
        self,
        storage: object,
        fill_kwargs: dict[str, list[float]],
        expected_values: list[float | int],
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(2, 0, 2, name="x"),
            storage=storage,
        )
        h.fill(x=[0.5, 1.5], **fill_kwargs)
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        assert result["values"] == pytest.approx(expected_values)
        assert "variances" not in result

    def test_missing_chunk_raises_key_error(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a"], name="cat"),
        )
        hist_id, entry = _make_entry(h)

        with pytest.raises(
            KeyError, match=r"chunk selection \{'cat': 'missing'\} not found"
        ):
            histogram_to_plot_json(hist_id, entry, selection={"cat": "missing"})

    def test_version_field_is_ms_timestamp(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        expected_version = int(entry.last_access.timestamp() * 1000)
        assert result["version"] == expected_version

    def test_name_and_label_forwarded(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"), name="my_hist", label="My Histogram"
        )
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        assert "name" not in result
        assert "label" not in result

    def test_2d_histogram_values_shape(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(3, 0, 3, name="x"),
            hist.axis.Regular(2, 0, 2, name="y"),
        )
        h.fill(x=[0.5, 1.5, 2.5], y=[0.5, 1.5, 0.5])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry, selection={})

        # values should be a 5x4 nested list with flow bins on both axes
        assert len(result["values"]) == 5
        assert len(result["values"][0]) == 4


class TestHistogramMetadata:
    def test_metadata_exposes_dense_schema_and_chunk_categories(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["data", "mc"], name="dataset"),
        )
        hist_id, entry = _make_entry(h)

        result = histogram_metadata(hist_id, entry)

        assert result["hist_id"] == hist_id
        assert len(result["dense_metadata"]["axes"]) == 1
        assert result["dense_metadata"]["axes"][0]["metadata"]["name"] == "x"
        assert result["chunk_axes"] == [
            {
                "name": "dataset",
                "label": "dataset",
                "type": "category_str",
                "categories": ["data", "mc"],
            }
        ]


class TestHistogramSummary:
    def test_basic_fields(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x", label="x-axis"), name="h", label="My H"
        )
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        assert result["hist_id"] == hist_id
        assert result["name"] == "h"
        assert result["label"] == "My H"
        assert result["token"] is None
        assert isinstance(result["bytes"], int)
        assert isinstance(result["last_access"], float)

    def test_regular_axis_summary(self) -> None:
        h = hist.Hist(hist.axis.Regular(10, 0, 5, name="pt"))
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        assert result["name"] == ""
        assert result["label"] == ""
        assert result["chunk_axes"] == []

    def test_str_category_summary(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b"], name="cat"),
        )
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        assert result["chunk_axes"] == [
            {
                "name": "cat",
                "label": "cat",
                "type": "category_str",
                "categories": ["a", "b"],
            }
        ]

    def test_no_values_in_summary(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        h.fill(x=[0.5, 1.5, 2.5])
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        assert "values" not in result
        assert "variances" not in result
        assert "dense_metadata" not in result
        assert "chunk_axes" in result

from __future__ import annotations

from datetime import datetime, timezone

import boost_histogram as bh
import hist
import numpy as np
import pytest

from histserv.chunked_hist import ChunkedHist
from histserv.dashboard.histogram_json import histogram_summary, histogram_to_plot_json
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

        result = histogram_to_plot_json(hist_id, entry)

        assert result["hist_id"] == hist_id
        assert result["axes"][0]["type"] == "Regular"
        assert result["axes"][0]["name"] == "x"
        assert result["axes"][0]["label"] == "x-axis"
        # Regular(4, 0, 4) → 5 edges: [0, 1, 2, 3, 4]
        assert len(result["axes"][0]["edges"]) == 5
        assert result["axes"][0]["edges"][0] == pytest.approx(0.0)
        assert result["axes"][0]["edges"][-1] == pytest.approx(4.0)
        # 4 bins, flow=False
        assert len(result["values"]) == 4
        assert result["values"][1] == pytest.approx(1.0)  # bin [1,2): one entry at 1.5

    def test_variable_axis_edges(self) -> None:
        edges = [0.0, 1.0, 3.0, 6.0]
        h = hist.Hist(hist.axis.Variable(edges, name="pt", label="p_{T}"))
        h.fill(pt=[0.5, 2.0, 4.0])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        assert result["axes"][0]["type"] == "Variable"
        assert result["axes"][0]["edges"] == pytest.approx(edges)

    def test_str_category_labels(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b", "c"], name="cat", label="category"),
        )
        h.fill(x=[0.5, 1.5, 2.5], cat=["a", "b", "c"])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        cat_axis = next(ax for ax in result["axes"] if ax["name"] == "cat")
        assert cat_axis["type"] == "StrCategory"
        assert cat_axis["labels"] == ["a", "b", "c"]
        assert "edges" not in cat_axis

    def test_int_category_labels(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.IntCategory([10, 20, 30], name="run", label="run number"),
        )
        h.fill(x=[0.5, 1.5, 2.5], run=[10, 20, 30])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        run_axis = next(ax for ax in result["axes"] if ax["name"] == "run")
        assert run_axis["type"] == "IntCategory"
        assert run_axis["labels"] == ["10", "20", "30"]

    def test_weight_storage_includes_variances(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            storage=bh.storage.Weight(),
        )
        h.fill(x=[0.5, 0.5, 1.5], weight=[1.0, 2.0, 3.0])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        assert result["storage_type"] == "Weight"
        assert "variances" in result
        assert len(result["variances"]) == 4
        # bin 0 ([0,1)): weights 1+2=3, variances 1^2+2^2=5
        assert result["values"][0] == pytest.approx(3.0)
        assert result["variances"][0] == pytest.approx(5.0)

    def test_double_storage_no_variances(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        h.fill(x=[0.5, 1.5])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        assert result["storage_type"] == "Double"
        assert "variances" not in result

    def test_version_field_is_ms_timestamp(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        expected_version = int(entry.last_access.timestamp() * 1000)
        assert result["version"] == expected_version

    def test_name_and_label_forwarded(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"), name="my_hist", label="My Histogram"
        )
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        assert result["name"] == "my_hist"
        assert result["label"] == "My Histogram"

    def test_2d_histogram_values_shape(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(3, 0, 3, name="x"),
            hist.axis.Regular(2, 0, 2, name="y"),
        )
        h.fill(x=[0.5, 1.5, 2.5], y=[0.5, 1.5, 0.5])
        hist_id, entry = _make_entry(h)

        result = histogram_to_plot_json(hist_id, entry)

        # values should be a 3x2 nested list
        assert len(result["values"]) == 3
        assert len(result["values"][0]) == 2


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

        ax = result["axes"][0]
        assert ax["type"] == "Regular"
        assert ax["bins"] == 10
        assert ax["range"] == pytest.approx([0.0, 5.0])

    def test_str_category_summary(self) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b"], name="cat"),
        )
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        cat_ax = next(ax for ax in result["axes"] if ax["name"] == "cat")
        assert cat_ax["type"] == "StrCategory"
        assert cat_ax["categories"] == 2

    def test_no_values_in_summary(self) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        h.fill(x=[0.5, 1.5, 2.5])
        hist_id, entry = _make_entry(h)

        result = histogram_summary(hist_id, entry)

        assert "values" not in result
        assert "variances" not in result

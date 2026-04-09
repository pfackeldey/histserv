from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from histserv.chunked_hist import ChunkedHist
from histserv.dashboard import create_app
from histserv.service import Histogrammer

import hist
import numpy as np


@pytest.fixture
def histogrammer() -> Histogrammer:
    return Histogrammer()


@pytest.fixture
def app_client(histogrammer: Histogrammer) -> TestClient:
    app = create_app(histogrammer)
    return TestClient(app)


def _add_hist(
    histogrammer: Histogrammer, h: hist.Hist, token: str | None = None
) -> str:
    """Directly insert a histogram into the histogrammer, returns hist_id."""
    from datetime import datetime, timezone
    import uuid

    hist_id = uuid.uuid4().hex
    chunked = ChunkedHist.from_hist(h)
    from histserv.service import HistogramEntry

    histogrammer._entries[hist_id] = HistogramEntry(
        hist=chunked,
        token=token,
        last_access=datetime.now(timezone.utc),
        unique_ids=set(),
    )
    return hist_id


class TestGetHistogramMetadata:
    def test_metadata_includes_dense_schema_and_chunk_categories(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["data", "mc"], name="dataset"),
        )
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(f"/api/histograms/{hist_id}/metadata")

        assert resp.status_code == 200
        data = resp.json()
        assert data["hist_id"] == hist_id
        assert len(data["dense_metadata"]["axes"]) == 1
        assert data["dense_metadata"]["axes"][0]["metadata"]["name"] == "x"
        assert data["chunk_axes"] == [
            {
                "name": "dataset",
                "label": "dataset",
                "type": "category_str",
                "categories": ["data", "mc"],
            }
        ]


class TestGetHistogram:
    def test_existing_histogram(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"), name="test")
        h.fill(x=[0.5, 1.5])
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(
            f"/api/histograms/{hist_id}",
            params={"selection": json.dumps({})},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["hist_id"] == hist_id
        assert data["selection"] == {}
        assert "values" in data
        assert len(data["values"]) == 6

    def test_selection_is_required(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(f"/api/histograms/{hist_id}")

        assert resp.status_code == 400
        assert "selection is required" in resp.json()["error"]

    def test_unknown_id_returns_404(self, app_client: TestClient) -> None:
        resp = app_client.get("/api/histograms/doesnotexist")

        assert resp.status_code == 404

    def test_token_protected_histogram_without_token_returns_404(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h, token="secret")

        resp = app_client.get(f"/api/histograms/{hist_id}")

        assert resp.status_code == 404

    def test_token_protected_histogram_with_correct_token(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h, token="secret")

        resp = app_client.get(
            f"/api/histograms/{hist_id}",
            params={"token": "secret", "selection": json.dumps({})},
        )

        assert resp.status_code == 200

    def test_str_category_histogram(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b"], name="cat"),
        )
        h.fill(x=[0.5, 1.5], cat=["a", "b"])
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(
            f"/api/histograms/{hist_id}",
            params={"selection": json.dumps({"cat": "a"})},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["selection"] == {"cat": "a"}
        assert len(data["values"]) == 6

    def test_chunked_histogram_rejects_incomplete_selection(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b"], name="cat"),
        )
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(
            f"/api/histograms/{hist_id}",
            params={"selection": json.dumps({})},
        )

        assert resp.status_code == 400
        assert "exactly one value for each chunk axis" in resp.json()["error"]

    def test_chunked_histogram_unknown_slice_returns_404(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a"], name="cat"),
        )
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(
            f"/api/histograms/{hist_id}",
            params={"selection": json.dumps({"cat": "missing"})},
        )

        assert resp.status_code == 404

from __future__ import annotations

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


def _add_hist(histogrammer: Histogrammer, h: hist.Hist, token: str | None = None) -> str:
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


class TestGetHistogram:
    def test_existing_histogram(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"), name="test")
        h.fill(x=[0.5, 1.5])
        hist_id = _add_hist(histogrammer, h)

        resp = app_client.get(f"/api/histograms/{hist_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["hist_id"] == hist_id
        assert data["name"] == "test"
        assert len(data["axes"]) == 1
        assert data["axes"][0]["type"] == "Regular"
        assert "values" in data

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

        resp = app_client.get(f"/api/histograms/{hist_id}?token=secret")

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

        resp = app_client.get(f"/api/histograms/{hist_id}")

        assert resp.status_code == 200
        data = resp.json()
        cat_axis = next(ax for ax in data["axes"] if ax["name"] == "cat")
        assert cat_axis["labels"] == ["a", "b"]

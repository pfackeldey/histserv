from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import hist

from histserv.chunked_hist import ChunkedHist
from histserv.dashboard import create_app
from histserv.service import HistogramEntry, Histogrammer


@pytest.fixture
def histogrammer() -> Histogrammer:
    return Histogrammer()


@pytest.fixture
def app_client(histogrammer: Histogrammer) -> TestClient:
    app = create_app(histogrammer)
    return TestClient(app)


def _add_hist(histogrammer: Histogrammer, h: hist.Hist) -> str:
    import uuid

    hist_id = uuid.uuid4().hex
    histogrammer._entries[hist_id] = HistogramEntry(
        hist=ChunkedHist.from_hist(h),
        token=None,
        last_access=datetime.now(timezone.utc),
        unique_ids=set(),
    )
    return hist_id


class TestWebSocketProtocol:
    def test_subscribe_stats_returns_stats_message(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        with app_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "payload": {"streams": ["stats"]}})
            msg = ws.receive_json()

        assert msg["type"] == "stats"
        assert "payload" in msg
        assert "ts" in msg
        payload = msg["payload"]
        assert "histogram_count" in payload
        assert "uptime_seconds" in payload
        assert "version" in payload

    def test_subscribe_hist_list_returns_hist_list_message(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"), name="myhist")
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "payload": {"streams": ["hist_list"]}})
            msg = ws.receive_json()

        assert msg["type"] == "hist_list"
        items = msg["payload"]["items"]
        assert any(item["hist_id"] == hist_id for item in items)
        item = next(i for i in items if i["hist_id"] == hist_id)
        assert item["name"] == "myhist"
        assert item["chunk_axes"] == []

    def test_subscribe_hist_returns_hist_data(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        h.fill(x=[0.5, 1.5, 2.5])
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "subscribe_hist",
                    "payload": {"hist_id": hist_id, "selection": {}},
                }
            )
            meta = ws.receive_json()
            data = ws.receive_json()

        assert meta["type"] == "hist_meta"
        assert meta["payload"]["hist_id"] == hist_id
        assert len(meta["payload"]["dense_metadata"]["axes"]) == 1

        assert data["type"] == "hist_data"
        assert data["payload"]["hist_id"] == hist_id
        assert data["payload"]["selection"] == {}
        assert "values" in data["payload"]

    def test_subscribe_hist_requires_selection(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe_hist", "payload": {"hist_id": hist_id}})
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert msg["payload"]["code"] == "INVALID_SELECTION"

    def test_subscribe_hist_slice_returns_dense_chunk(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(
            hist.axis.Regular(4, 0, 4, name="x"),
            hist.axis.StrCategory(["a", "b"], name="cat"),
        )
        h.fill(x=[0.5, 1.5], cat=["a", "b"])
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "subscribe_hist",
                    "payload": {"hist_id": hist_id, "selection": {"cat": "a"}},
                }
            )
            meta = ws.receive_json()
            data = ws.receive_json()

        assert meta["type"] == "hist_meta"
        assert meta["payload"]["chunk_axes"] == [
            {
                "name": "cat",
                "label": "cat",
                "type": "category_str",
                "categories": ["a", "b"],
            }
        ]
        assert data["type"] == "hist_data"
        assert data["payload"]["selection"] == {"cat": "a"}

    def test_get_hist_one_shot(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "get_hist",
                    "payload": {"hist_id": hist_id, "selection": {}},
                }
            )
            meta = ws.receive_json()
            data = ws.receive_json()

        assert meta["type"] == "hist_meta"
        assert data["type"] == "hist_data"
        assert data["payload"]["hist_id"] == hist_id
        assert data["payload"]["selection"] == {}

    def test_get_hist_unknown_id_returns_error(self, app_client: TestClient) -> None:
        with app_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "get_hist", "payload": {"hist_id": "doesnotexist"}})
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert msg["payload"]["code"] == "NOT_FOUND"

    def test_subscribe_and_unsubscribe_hist(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        h = hist.Hist(hist.axis.Regular(4, 0, 4, name="x"))
        hist_id = _add_hist(histogrammer, h)

        with app_client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "subscribe_hist",
                    "payload": {"hist_id": hist_id, "selection": {}},
                }
            )
            assert ws.receive_json()["type"] == "hist_meta"
            assert ws.receive_json()["type"] == "hist_data"

            # Unsubscribe; no more messages should arrive for this hist
            ws.send_json(
                {
                    "type": "unsubscribe_hist",
                    "payload": {"hist_id": hist_id, "selection": {}},
                }
            )
            # Subscribe stats to get another message (proves connection is still alive)
            ws.send_json({"type": "subscribe", "payload": {"streams": ["stats"]}})
            msg2 = ws.receive_json()
            assert msg2["type"] == "stats"

    def test_message_envelope_structure(
        self, app_client: TestClient, histogrammer: Histogrammer
    ) -> None:
        """Every server message must have type, ts, and payload fields."""
        with app_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "payload": {"streams": ["stats"]}})
            msg = ws.receive_json()

        assert "type" in msg
        assert "ts" in msg
        assert "payload" in msg
        assert isinstance(msg["ts"], float)
        assert isinstance(msg["type"], str)
        assert isinstance(msg["payload"], dict)

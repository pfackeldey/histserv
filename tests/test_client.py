from __future__ import annotations

from histserv.client import Client


def test_exit_without_rpc_does_not_create_channel() -> None:
    with Client("localhost:1") as client:
        pass
    assert "channel" not in client.__dict__


def test_exit_closes_created_channel() -> None:
    with Client("localhost:1") as client:
        _ = client.channel
    assert "channel" in client.__dict__

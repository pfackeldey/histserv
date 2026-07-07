from __future__ import annotations

import json
import subprocess
import sys

_IMPORT_PROBE = """
import json
import logging

logging.basicConfig(level=logging.WARNING)
root = logging.getLogger()
handler_before = root.handlers[0]

import histserv  # noqa: F401

print(
    json.dumps(
        {
            "level": root.level,
            "handler_count": len(root.handlers),
            "handler_preserved": root.handlers[0] is handler_before,
        }
    )
)
"""


def test_import_does_not_reconfigure_root_logger() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    probe = json.loads(result.stdout)
    assert probe["level"] == 30  # logging.WARNING, as set by the host app
    assert probe["handler_count"] == 1
    assert probe["handler_preserved"] is True

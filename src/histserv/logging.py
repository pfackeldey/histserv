from __future__ import annotations

import logging
from datetime import datetime

_CONFIGURED = False

fmt_rpc_logger_msg = "RPC<{rpc_method}> - {msg} (hist_id={hist_id})".format
fmt_rpc_logger_msg_no_hist_id = "RPC<{rpc_method}> - {msg}".format
fmt_callback_logger_msg = "Callback<{callback_method}> - {msg}".format


class _MillisecondFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None) -> str:
        del datefmt  # unused
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(record.msecs):03d}"


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger().setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        _MillisecondFormatter("%(asctime)s %(levelname)s:%(name)s:%(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)

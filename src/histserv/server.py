from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from concurrent import futures
from functools import partial
import json
import uuid
import threading

import grpc
import hist
import hist.serialization
import numpy as np
import uhi.io.json


from histserv.protos import hist_pb2, hist_pb2_grpc
from histserv.serialize import deserialize, serialize
from histserv.util import bytes_repr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("histserv")


# little helpers to format logger calls
fmt_rpc_logger_msg = "RPC<{rpc_method}> (hist_id={hist_id}) - {msg}".format
fmt_callback_logger_msg = "Callback<{callback_method}> - {msg}".format


class Histogrammer(hist_pb2_grpc.HistogrammerServiceServicer):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._hists = {}
        self._hists_last_access = {}

    @property
    def hists(self) -> dict:
        return self._hists

    @property
    def hists_last_access(self) -> dict:
        return self._hists_last_access

    async def Init(
        self, request: hist_pb2.InitRequest, context: grpc.ServicerContext
    ) -> hist_pb2.InitResponse:
        # generate unique key
        H_id = uuid.uuid4().hex

        fmt_rpc_msg = partial(fmt_rpc_logger_msg, rpc_method="Init", hist_id=H_id)

        # make sure it doesn't exist (should basically never happen)
        if H_id in self.hists:
            error_msg = f"try again; init failed due to existing key (key={H_id})."
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.InitResponse(success=False, message=error_msg)

        # deserialize message to histogram
        H = hist.Hist(
            json.loads(request.hist_json, object_hook=uhi.io.json.object_hook)
        )

        with self._lock:
            # store histogram
            self.hists_last_access[H_id] = datetime.now()
            self.hists[H_id] = H

        success_msg = "initialized histogram"
        logger.info(fmt_rpc_msg(msg=success_msg))

        # return H_id to client to access it again
        return hist_pb2.InitResponse(success=True, message=H_id)

    async def Fill(
        self, request: hist_pb2.FillRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FillResponse:
        del context  # unused

        H_id = request.hist_id
        fmt_rpc_msg = partial(fmt_rpc_logger_msg, rpc_method="Fill", hist_id=H_id)

        try:
            # Deserialize the message from the request
            kwargs = {key: deserialize(msg) for key, msg in request.kwargs.items()}
        except Exception as e:
            error_msg = f"error deserializing request: {e!r}"
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.FillResponse(success=False, message=error_msg)
        try:
            with self._lock:
                self.hists_last_access[H_id] = datetime.now()
                self.hists[H_id].fill(**kwargs)
                nbytes_filled = sum(
                    [nd.nbytes for nd in kwargs.values() if isinstance(nd, np.ndarray)]
                )
                success_msg = f"filled with {bytes_repr(nbytes_filled)}"
                logger.info(fmt_rpc_msg(msg=success_msg))
            return hist_pb2.FillResponse(success=True, message=success_msg)
        except Exception as e:
            error_msg = f"error filling histogram: {e!r}"
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.FillResponse(success=False, message=error_msg)

    async def SnapShot(
        self, request: hist_pb2.SnapShotRequest, context: grpc.ServicerContext
    ) -> hist_pb2.SnapShotResponse:
        del context  # unused

        H_id = request.hist_id
        fmt_rpc_msg = partial(fmt_rpc_logger_msg, rpc_method="SnapShot", hist_id=H_id)

        try:
            with self._lock:
                self.hists_last_access[H_id] = datetime.now()
                if request.drop_from_server:
                    H = self.hists.pop(H_id)
                else:
                    H = self.hists[H_id]

            # serialize
            H_ser = hist.serialization.to_uhi(H)
            storage = H_ser.pop("storage")
            # recover type
            H_ser["storage"] = {"type": storage.pop("type")}

            # serialize all contents
            data_ser = {k: serialize(v) for k, v in storage.items()}

            success_msg = "created snapshot"
            logger.info(fmt_rpc_msg(msg=success_msg))

            return hist_pb2.SnapShotResponse(
                success=True,
                message=success_msg,
                hist_json=json.dumps(H_ser),  # pure metadata
                data=data_ser,  # heavy contents
            )

        except Exception as e:
            error_msg = f"failed creating a snapshot of histogram: {e!r}"
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.SnapShotResponse(
                success=False, message=error_msg, hist_json="", data={}
            )

    async def Flush(
        self, request: hist_pb2.FlushRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FlushResponse:
        import h5py
        import uhi.io.hdf5

        del context  # unused

        H_id = request.hist_id
        destination = request.destination
        fmt_rpc_msg = partial(fmt_rpc_logger_msg, rpc_method="Flush", hist_id=H_id)

        if not destination.endswith((".h5", ".hdf5")):
            error_msg = f"invalid destination: {destination}, needs to be a hdf5 file, e.g., 'hist.hdf5'"
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.FlushResponse(success=False, message=error_msg)

        try:
            self.hists_last_access[H_id] = datetime.now()
            H = self.hists[H_id]
            with h5py.File(destination, "w") as h5_file:
                uhi.io.hdf5.write(h5_file.create_group(H_id), H)

            with self._lock:
                # flushing means we evict it from the server's memory
                self.hists.pop(H_id, None)
                self.hists_last_access.pop(H_id, None)

            success_msg = f"flushed histogram to {destination}"
            logger.info(fmt_rpc_msg(msg=success_msg))

            return hist_pb2.FlushResponse(
                success=True,
                message=success_msg,
            )
        except Exception as e:
            error_msg = f"error flushing histogram: {e!r} to {destination}"
            logger.error(fmt_rpc_msg(msg=error_msg))
            return hist_pb2.FlushResponse(success=False, message=error_msg)


# Callback: remove old hists to make the server memory not explode with long uptimes
async def prune_old_hists(histogrammer: Histogrammer, delta: timedelta) -> None:
    while True:
        now = datetime.now()
        drop_ids = set()
        for H_id, last_access in histogrammer.hists_last_access.items():
            if (now - last_access) >= delta:
                drop_ids.add(H_id)

        with histogrammer._lock:
            for H_id in drop_ids:
                logger.info(
                    fmt_callback_logger_msg(
                        callback_method="prune_old_hists",
                        msg=f"dropping histogram ({H_id}) because it hasn't been accessed since {delta}",
                    )
                )
                histogrammer.hists_last_access.pop(H_id, None)
                histogrammer.hists.pop(H_id, None)

        # check freq: 5min (todo: make it configurable)
        await asyncio.sleep(60 * 5)


# Callback: log every n seconds how much memory the hists on the server use
async def print_hists_stats(histogrammer: Histogrammer) -> None:
    while True:
        if histogrammer.hists:
            nbytes = 0
            nhists = len(histogrammer.hists)
            for H in histogrammer.hists.values():
                nbytes += H.view(True).nbytes

            logger.info(
                fmt_callback_logger_msg(
                    callback_method="print_hists_stats",
                    msg=f"using {bytes_repr(nbytes)} with {nhists} hists",
                )
            )

        # check freq: 5s (todo: make it configurable)
        await asyncio.sleep(5)


class Server:
    def __init__(
        self,
        port: int = 50051,
        n_threads: int = 1,
    ) -> None:
        self.port = port
        self.n_threads = n_threads

        # create gRPC server
        self.server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=n_threads),
            # compression=grpc.Compression.Gzip,
            compression=grpc.Compression.NoCompression,  # turn off for now, we compress with numcodecs the byte buffer
            options=[
                ("grpc.max_receive_message_length", 1 << 29),
            ],
        )
        # add service
        histogrammer = Histogrammer()
        hist_pb2_grpc.add_HistogrammerServiceServicer_to_server(
            histogrammer, self.server
        )

        # add callbacks:
        # - prune hists that haven't been filled/snapshotted/etc since more than 1 day (todo: make it configurable)
        # - print hists stats to understand current memory usage
        self._callbacks = [
            asyncio.create_task(
                prune_old_hists(histogrammer=histogrammer, delta=timedelta(days=1))
            ),
            asyncio.create_task(
                print_hists_stats(histogrammer=histogrammer),
            ),
        ]

        # add port
        self.server.add_insecure_port(self.address)

    @property
    def address(self) -> str:
        return f"[::]:{self.port}"

    @property
    def callbacks(self) -> list[asyncio.Task]:
        return self._callbacks

    async def start(self) -> None:
        await self.server.start()
        logger.info(
            f"started - listening on {self.address} with {self.n_threads} threads"
        )

    async def stop(self, grace: float | None = None) -> None:
        await self.server.stop(grace=grace)

    async def wait_for_termination(self, timeout: float | None = None) -> None:
        await self.server.wait_for_termination(timeout=timeout)

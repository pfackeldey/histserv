from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from concurrent import futures
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("histserv")


async def prune_old_hists(histogrammer: Histogrammer, delta: timedelta) -> None:
    while True:
        now = datetime.now()
        drop_ids = set()
        for H_id, last_access in histogrammer.hists_last_access.items():
            if (now - last_access) > delta:
                drop_ids.add(H_id)

        with histogrammer._lock:
            for H_id in drop_ids:
                logger.info(
                    f"Dropping histogram ({H_id}) because it hasn't been accessed since {delta}"
                )
                histogrammer.hists_last_access.pop(H_id, None)
                histogrammer.hists.pop(H_id, None)

        # check freq: 5min (todo: make it configurable)
        await asyncio.sleep(60 * 5)


class Histogrammer(hist_pb2_grpc.HistogrammerServiceServicer):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._hists = {}
        self._hists_last_access = {}

        # add callbacks:
        # - prune hists that haven't been filled/snapshotted/etc since more than 1 day (todo: make it configurable)
        asyncio.create_task(prune_old_hists(histogrammer=self, delta=timedelta(days=1)))

    @property
    def hists(self):
        return self._hists

    @property
    def hists_last_access(self):
        return self._hists_last_access

    async def Init(
        self, request: hist_pb2.InitRequest, context: grpc.ServicerContext
    ) -> hist_pb2.InitResponse:
        with self._lock:
            # generate unique key
            H_id = uuid.uuid4().hex

            # make sure it doesn't exist (should basically never happen)
            if H_id in self.hists:
                return hist_pb2.InitResponse(
                    success=False,
                    message="try again; init failed due to existing key.",
                )

            # deserialize message to histogram
            H = hist.Hist(
                json.loads(request.hist_json, object_hook=uhi.io.json.object_hook)
            )

            # store histogram
            self.hists_last_access[H_id] = datetime.now()
            self.hists[H_id] = H

            logger.info(f"Initialized histogram ({H_id})")

        # return H_id to client to access it again
        return hist_pb2.InitResponse(
            success=True,
            message=H_id,
        )

    async def Fill(
        self, request: hist_pb2.FillRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FillResponse:
        del context  # unused

        H_id = request.hist_id

        try:
            # Deserialize the message from the request
            kwargs = {key: deserialize(msg) for key, msg in request.kwargs.items()}
        except Exception as e:
            return hist_pb2.FillResponse(
                success=False, message=f"Error deserializing request: {e!r}"
            )
        try:
            with self._lock:
                self.hists_last_access[H_id] = datetime.now()
                self.hists[H_id].fill(**kwargs)
                nbytes_filled = sum(
                    [nd.nbytes for nd in kwargs.values() if isinstance(nd, np.ndarray)]
                )
                logger.info(f"Filled histogram ({H_id}) with {nbytes_filled:,} bytes")
            return hist_pb2.FillResponse(success=True, message=None)
        except Exception as e:
            return hist_pb2.FillResponse(
                success=False, message=f"Error filling histogram ({H_id}): {e!r}"
            )

    async def SnapShot(
        self, request: hist_pb2.SnapShotRequest, context: grpc.ServicerContext
    ) -> hist_pb2.SnapShotResponse:
        del context  # unused

        H_id = request.hist_id

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

            return hist_pb2.SnapShotResponse(
                success=True,
                message="",
                hist_json=json.dumps(H_ser),  # pure metadata
                data=data_ser,  # heavy contents
            )

        except Exception as e:
            return hist_pb2.SnapShotResponse(
                success=False,
                message=f"Failed creating a snapshot of histogram ({H_id}): {e!r}",
                hist_json="",
                data={},
            )

    async def Flush(
        self, request: hist_pb2.FlushRequest, context: grpc.ServicerContext
    ) -> hist_pb2.FlushResponse:
        import h5py
        import uhi.io.hdf5

        del context  # unused

        H_id = request.hist_id
        destination = request.destination

        if not destination.endswith((".h5", ".hdf5")):
            return hist_pb2.FlushResponse(
                success=False,
                message=f"Invalid destination: {destination}, needs to be a hdf5 file, e.g., 'hist.hdf5'.",
            )

        try:
            with self._lock:
                self.hists_last_access[H_id] = datetime.now()
                H = self.hists[H_id]
                with h5py.File(destination, "w") as h5_file:
                    uhi.io.hdf5.write(h5_file.create_group("histogram"), H)

                # flushing means we evict it from the server's memory
                self.hists.pop(H_id, None)

                logger.info(f"Flushed histogram ({H_id}) to {destination}")
            return hist_pb2.FlushResponse(
                success=True,
                message=f"Histogram ({H_id}) flushed successfully to {destination}.",
            )
        except Exception as e:
            return hist_pb2.FlushResponse(
                success=False,
                message=f"Error flushing histogram ({H_id}): {e!r} to {destination}",
            )


class Server:
    def __init__(self, port: int = 50051, n_threads: int = 1) -> None:
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

        # add port
        self.server.add_insecure_port(self.address)

    @property
    def address(self) -> str:
        return f"[::]:{self.port}"

    async def start(self) -> None:
        await self.server.start()
        logger.info(
            f"Histogram server started, listening on {self.address} with {self.n_threads} threads"
        )

    async def stop(self, grace: float | None = None) -> None:
        await self.server.stop(grace=grace)

    async def wait_for_termination(self, timeout: float | None = None) -> None:
        await self.server.wait_for_termination(timeout=timeout)

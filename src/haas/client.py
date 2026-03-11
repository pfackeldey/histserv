from __future__ import annotations

import logging
import typing as tp
from functools import cached_property

import grpc
from hist import Hist
import json
import uhi.io.json

from haas.protos import hist_pb2, hist_pb2_grpc
from haas.serialize import serialize, deserialize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HaaSClient:
    def __init__(self, address: str) -> None:
        self.address = address

    def __getstate__(self):
        state = dict(self.__dict__)
        state.pop("channel", None)
        return state

    def __enter__(self) -> HaaSClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback  # unused
        self.channel.close()

    @cached_property
    def channel(self) -> grpc.Channel:
        return grpc.insecure_channel(
            self.address,
            # compression=grpc.Compression.Gzip,
            compression=grpc.Compression.NoCompression,  # turn off for now, we compress with numcodecs the byte buffer
            options=[
                ("grpc.max_send_message_length", 1 << 29),
            ],
        )

    @property
    def stub(self) -> hist_pb2_grpc.HistogrammerServiceStub:
        return hist_pb2_grpc.HistogrammerServiceStub(self.channel)

    def init(self, hist: Hist) -> RemoteHist:
        if not isinstance(hist, Hist):
            raise ValueError(f"`hist` must of type `hist.Hist`, got {type(hist)=}")

        # TODO: replace with metadata only serialization once this is resolved:
        # https://github.com/scikit-hep/boost-histogram/issues/1089
        json_obj = json.dumps(hist, default=uhi.io.json.default)
        request = hist_pb2.InitRequest(hist_json=json_obj)

        ret = self.stub.Init(request)
        if not ret.success:
            raise ValueError(ret.message)

        # create a remote hist that one can interact with
        return RemoteHist(client=self, hist_id=ret.message)


class RemoteHist:
    __slots__ = ("_client", "_hist_id")

    def __init__(self, client: HaaSClient, hist_id: str) -> None:
        self._client = client
        self._hist_id = hist_id

    @property
    def client(self) -> HaaSClient:
        return self._client

    @property
    def hist_id(self) -> str:
        return self._hist_id

    def __repr__(self) -> str:
        return f"RemoteHist<ID={self.hist_id} @{self.client.address}>"

    def fill(self, **kwargs: tp.Any) -> grpc.Future[hist_pb2.FillResponse]:
        serialized_kwargs = {key: serialize(value) for key, value in kwargs.items()}
        request = hist_pb2.FillRequest(hist_id=self.hist_id, kwargs=serialized_kwargs)
        return self.client.stub.Fill.future(request)

    def snapshot(self, drop_from_server: bool = False) -> Hist:
        request = hist_pb2.SnapShotRequest(
            hist_id=self.hist_id, drop_from_server=drop_from_server
        )
        ret = self.client.stub.SnapShot(request)
        if not ret.success:
            raise ValueError(ret.message)

        hist_json = json.loads(ret.hist_json)
        content_ser = ret.data
        content = {k: deserialize(v) for k, v in content_ser.items()}

        hist_json["storage"].update(content)
        return Hist(hist_json)

    def flush(
        self, destination: str = "hist.coffea"
    ) -> grpc.Future[hist_pb2.FlushResponse]:
        request = hist_pb2.FlushRequest(hist_id=self.hist_id, destination=destination)
        return self.client.stub.Flush.future(request)

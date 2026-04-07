from __future__ import annotations

import grpc
import hist
import numpy as np

from histserv import Client, RemoteHist


def main() -> None:
    local_hist = hist.Hist(
        hist.axis.Regular(8, -4, 4, name="x", label="X Axis"),
        hist.axis.StrCategory([], growth=True, name="dataset", label="Dataset"),
        storage=hist.storage.Weight(),
    )

    with Client(address="[::]:50051") as client:
        remote_hist = client.init(local_hist, token="alice")
        print("Initialized:", remote_hist)

        print("Exists right after init:", remote_hist.exists())

        remote_hist.fill_many(
            [
                {
                    "x": np.array([-1.0, 0.0, 1.0], dtype=np.float64),
                    "dataset": "data",
                    "weight": np.ones(3, dtype=np.float64),
                },
                {
                    "x": np.array([0.5, 1.5], dtype=np.float64),
                    "dataset": "mc",
                    "weight": np.ones(2, dtype=np.float64),
                },
            ]
        )
        print("fill_many succeeded.")

        snapshot = remote_hist.snapshot()
        print("Full snapshot as ChunkedHist:", snapshot)
        print("Materialized local hist:", snapshot.to_hist())

        data_only = remote_hist[{"dataset": "data"}].snapshot()
        print("Slice snapshot:", data_only.to_hist())

        connection_info = remote_hist.get_connection_info()
        print("Connection info:", connection_info)

        # Reconnect using an existing client
        reconnected_direct = client.connect(
            remote_hist.hist_id,
            token=remote_hist.token,
        )
        print("Direct reconnect exists:", reconnected_direct.exists())

        # Reconnect using the histogram's connection info
        reconnected = RemoteHist.from_connection_info(connection_info)
        reconnected.fill(
            x=np.array([2.0], dtype=np.float64),
            dataset="data",
            weight=np.array([1.0], dtype=np.float64),
        )
        print("Reconnect + fill succeeded.")

        print("Stats:", client.stats(token="alice"))

        remote_hist.reset()
        print("After reset:", remote_hist.snapshot().to_hist())

        remote_hist.delete()
        print("Exists after delete:", remote_hist.exists())


if __name__ == "__main__":
    try:
        main()
    except grpc.RpcError as exc:
        print(f"RPC failed: {exc.code()} - {exc.details()}")

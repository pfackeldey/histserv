from __future__ import annotations

import grpc
import hist
import numpy as np

from histserv import Client


# some histogram to fill
H = hist.Hist(
    hist.axis.Regular(10, -2, 2, name="x", label="X Axis"),
    hist.axis.Regular(10, -2, 2, name="y", label="Y Axis"),
    hist.axis.StrCategory(
        ["data", "drell-yan"], name="dataset", label="Dataset", growth=True
    ),
    storage=hist.storage.Weight(),
)


if __name__ == "__main__":
    try:
        # connect to remote HistServ gRPC server
        with Client(address="[::]:50051") as client:
            # initialize it on the server and receive a 'remote_hist' to interact with it
            remote_hist = client.init(H)

            print("Remote hist initialized:", remote_hist)

            # fill histogram remotely (blocking operation)
            remote_hist.fill(
                x=np.random.normal(size=1_000_000).astype(np.float64),
                y=np.random.normal(size=1_000_000).astype(np.float64),
                dataset="data",
                weight=np.ones(1_000_000, dtype=np.float64),
            )
            print("Remote hist fill succeeded.")

            # Creating a snapshot means to return the current state of the remote_hist to the client
            # The `delete_from_server` option allows to remove the histogram from the server's memory if set to True
            print(
                "Snapshotting current hist:",
                remote_hist.snapshot(delete_from_server=False),
            )

            # fill histogram remotely again with different dataset
            remote_hist.fill(
                x=np.random.normal(size=1_000_000).astype(np.float64),
                y=np.random.normal(size=1_000_000).astype(np.float64),
                dataset="drell-yan",
                weight=np.ones(1_000_000, dtype=np.float64),
            )
            print("Remote hist fill succeeded.")

            # fill histogram remotely again with different dataset (something that triggers axis growth)
            remote_hist.fill(
                x=np.random.normal(size=1_000_000).astype(np.float64),
                y=np.random.normal(size=1_000_000).astype(np.float64),
                dataset="ttbar",
                weight=np.ones(1_000_000, dtype=np.float64),
            )
            print("Remote hist fill succeeded.")

            # flush histogram remotely to file
            remote_hist.flush(destination="hist.h5")
            print("Remote hist flushed successfully to hist.h5.")
    except grpc.RpcError as exc:
        print(f"RPC failed: {exc.code()} - {exc.details()}")

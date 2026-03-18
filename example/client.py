from __future__ import annotations

import hist
import numpy as np

from histserv import HistServClient


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
    # connect to remote HistServ gRPC server
    with HistServClient(address="[::]:50051") as client:
        # initialize it on the server and receive a 'remote_hist' to interact with it
        remote_hist = client.init(H)

        print("Remote hist initialized:", remote_hist)

        # fill histogram remotely (blocking operation)
        response = remote_hist.fill(
            x=np.random.normal(size=1_000_000).astype(np.float64),
            y=np.random.normal(size=1_000_000).astype(np.float64),
            dataset="data",
            weight=np.ones(1_000_000, dtype=np.float64),
        )
        print(f"Histogram remote_hist received: {response}")

        # Creating a snapshot means to return the current state of the remote_hist to the client
        # The `drop_from_server` option allows to remove the histogram from the server's memory if set to True
        print(
            "Snapshotting current hist:",
            remote_hist.snapshot(drop_from_server=False),
            "\n",
        )

        # fill histogram remotely again with different dataset
        response = remote_hist.fill(
            x=np.random.normal(size=1_000_000).astype(np.float64),
            y=np.random.normal(size=1_000_000).astype(np.float64),
            dataset="drell-yan",
            weight=np.ones(1_000_000, dtype=np.float64),
        )
        print(f"Histogram remote_hist received: {response}")

        # fill histogram remotely again with different dataset (something that triggers axis growth)
        response = remote_hist.fill(
            x=np.random.normal(size=1_000_000).astype(np.float64),
            y=np.random.normal(size=1_000_000).astype(np.float64),
            dataset="ttbar",
            weight=np.ones(1_000_000, dtype=np.float64),
        )
        print(f"Histogram remote_hist received: {response}")

        # flush histogram remotely to file
        response = remote_hist.flush(destination="hist.h5")
        print(f"Histogram remote_hist received: {response.message}")

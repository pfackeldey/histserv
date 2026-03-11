import hist
from haas import HaaSClient


class Processor:
    def __init__(self, haas_client: HaaSClient):
        # setup a histogram to fill
        H = hist.Hist(
            hist.axis.Regular(10, -2, 2, name="x", label="X Axis"),
            hist.axis.Regular(10, -2, 2, name="y", label="Y Axis"),
            hist.axis.StrCategory(
                ["data", "drell-yan"], name="dataset", label="Dataset", growth=True
            ),
            storage=hist.storage.Weight(),
        )

        # initialize it on the server and receive a 'remote_hist' to interact with it
        # do that only once on the host machine, every `init` will initialize a new
        # histogram to fill on the server, but we only want to do that once and fill that one
        self.remote_hist = haas_client.init(H)

    def process(self, events):
        # simple example fill
        import numpy as np

        futures = []
        for _ in range(4):
            future = self.remote_hist.fill(
                x=np.random.normal(size=1_000_000).astype(np.float64),
                y=np.random.normal(size=1_000_000).astype(np.float64),
                dataset="data",
                weight=np.ones(1_000_000, dtype=np.float64),
            )
            futures.append(future)

        # ensure that all of the remote hist fill calls succeeded
        if not all(f.result().success for f in futures):
            print(
                "Got some failures in remote hist filling:", [f.status for f in futures]
            )

        print("All remote fills succeeded!")

        # no need to return something, we filled already remotely
        return None


if __name__ == "__main__":
    client = HaaSClient(address="[::]:50051")

    myanalysis = Processor(haas_client=client)

    # check pickling works for coffea dask workflows
    import pickle

    myanalysis = pickle.loads(pickle.dumps(myanalysis))

    # run analysis
    myanalysis.process(events=None)

    print("Output hist:", myanalysis.remote_hist.snapshot())

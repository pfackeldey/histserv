import time

import numpy as np
from hist import Hist
from histserv import Client

RNG = np.random.default_rng(seed=42)
FILL_INTERVAL = 2.0  # seconds between fills
BATCH_SIZE = 500     # samples per fill

# Two histograms to make the dashboard more interesting
H_gauss = Hist.new.Reg(30, -3, 3, name="x", label="x-axis [a.u.]").Double()
H_wide  = Hist.new.Reg(40, -6, 6, name="y", label="y-axis [a.u.]").Double()

with Client(address="[::]:50051") as client:
    R_gauss = client.init(H_gauss)
    R_wide  = client.init(H_wide)
    print(f"Initialized  gaussian  → {R_gauss.hist_id}")
    print(f"Initialized  wide      → {R_wide.hist_id}")
    print(f"Filling every {FILL_INTERVAL}s with {BATCH_SIZE} samples each.  Ctrl-C to stop.\n")

    fill_number = 0
    total_entries = 0
    try:
        while True:
            fill_number += 1
            total_entries += BATCH_SIZE

            R_gauss.fill(x=RNG.standard_normal(BATCH_SIZE))
            R_wide.fill(y=RNG.standard_normal(BATCH_SIZE) * 2)

            snapshot_gauss = R_gauss.snapshot()
            peak = float(snapshot_gauss.to_hist().values().max())

            print(
                f"[fill #{fill_number:4d}]  "
                f"total entries: {total_entries:>7,}  |  "
                f"gaussian peak bin: {peak:.1f}  |  "
                f"ts: {time.strftime('%H:%M:%S')}"
            )
            time.sleep(FILL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.  Histograms remain on server (not deleted).")

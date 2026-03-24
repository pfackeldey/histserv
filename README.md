# Histogramming as a Service (HistServ)

[![PyPI version][pypi-version]][pypi-link]
[![Conda-Forge][conda-badge]][conda-link]
[![PyPI platforms][pypi-platforms]][pypi-link]

## Install from PyPI
```shell
pip install histserv
```

## Install from conda-forge
```shell
conda install -c conda-forge histserv
```

## Quickstart

Start gRPC server (or just `./example/start_server.sh`):
```shell
histserv --port 50051 --n-threads 4
# 2026-03-24 11:58:00.643 INFO:histserv:server (listening at [::]:50051) started with port=50051, n_threads=4, prune_after=24.00 h, prune_interval=5.00 min, stats_interval=5.00 s
```

Then run:
```python
from hist import Hist
from histserv import Client
import numpy as np


# initialize hist locally
H_local = Hist.new.Reg(30, -3, 3, name="x", label="x-axis").Double()

with Client(address="[::]:50051") as client:
    # initialize it on the server and receive a remote hist to interact with it
    H_remote = client.init(H_local)
    # fill the remote hist on the server
    H_remote.fill(x=np.random.normal(size=1000))
    # retrieve it back, drop it from the server & print it
    print(H_remote.snapshot(delete_from_server=True))


# local hist hasn't been filled
assert np.all(H_local.view(True) == 0)
```

Output in ipython:
```shell
┌────────────────────────────────────────────────────────────────────────────┐
[-inf,   -3) 1  │▋                                                           │
[  -3, -2.8) 0  │                                                            │
[-2.8, -2.6) 1  │▋                                                           │
[-2.6, -2.4) 1  │▋                                                           │
[-2.4, -2.2) 6  │████                                                        │
[-2.2,   -2) 11 │███████▍                                                    │
[  -2, -1.8) 12 │████████                                                    │
[-1.8, -1.6) 20 │█████████████▍                                              │
[-1.6, -1.4) 19 │████████████▊                                               │
[-1.4, -1.2) 33 │██████████████████████▏                                     │
[-1.2,   -1) 50 │█████████████████████████████████▌                          │
[  -1, -0.8) 70 │██████████████████████████████████████████████▉             │
[-0.8, -0.6) 49 │████████████████████████████████▉                           │
[-0.6, -0.4) 88 │███████████████████████████████████████████████████████████ │
[-0.4, -0.2) 63 │██████████████████████████████████████████▎                 │
[-0.2,    0) 65 │███████████████████████████████████████████▋                │
[   0,  0.2) 85 │█████████████████████████████████████████████████████████   │
[ 0.2,  0.4) 77 │███████████████████████████████████████████████████▋        │
[ 0.4,  0.6) 65 │███████████████████████████████████████████▋                │
[ 0.6,  0.8) 61 │████████████████████████████████████████▉                   │
[ 0.8,    1) 63 │██████████████████████████████████████████▎                 │
[   1,  1.2) 45 │██████████████████████████████▏                             │
[ 1.2,  1.4) 36 │████████████████████████▏                                   │
[ 1.4,  1.6) 32 │█████████████████████▌                                      │
[ 1.6,  1.8) 15 │██████████                                                  │
[ 1.8,    2) 11 │███████▍                                                    │
[   2,  2.2) 10 │██████▊                                                     │
[ 2.2,  2.4) 3  │██                                                          │
[ 2.4,  2.6) 5  │███▍                                                        │
[ 2.6,  2.8) 2  │█▍                                                          │
[ 2.8,    3) 1  │▋                                                           │
[   3,  inf) 0  │                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```


## Examples

See `example/` for more examples.

Run example client:
```shell
python example/client.py
# Remote hist initialized: RemoteHist<ID=52c77c93da8146f2a72c53af269d1ab5 @[::]:50051>
# Remote hist fill succeeded.
# Snapshotting current hist: Hist(
#   Regular(10, -2, 2, name='x', label='X Axis'),
#   Regular(10, -2, 2, name='y', label='Y Axis'),
#   StrCategory(['data', 'drell-yan'], growth=True, name='dataset', label='Dataset'),
#   storage=Weight()) # Sum: WeightedSum(value=911503, variance=911503) (WeightedSum(value=1e+06, variance=1e+06) with flow)
# Remote hist fill succeeded.
# Remote hist fill succeeded.
# Remote hist flushed successfully to hist.h5.
```

And the server logs additionally (after running the client script):
```shell
2026-03-24 11:58:29.113 INFO:histserv:RPC<Init> - initialized histogram (hist_id=52c77c93da8146f2a72c53af269d1ab5)
2026-03-24 11:58:29.189 INFO:histserv:RPC<Fill> - filled with 24.00 MB of decompressed arrays (hist_id=52c77c93da8146f2a72c53af269d1ab5)
2026-03-24 11:58:29.190 INFO:histserv:RPC<Snapshot> - created snapshot (hist_id=52c77c93da8146f2a72c53af269d1ab5)
2026-03-24 11:58:29.237 INFO:histserv:RPC<Fill> - filled with 24.00 MB of decompressed arrays (hist_id=52c77c93da8146f2a72c53af269d1ab5)
2026-03-24 11:58:29.282 INFO:histserv:RPC<Fill> - filled with 24.00 MB of decompressed arrays (hist_id=52c77c93da8146f2a72c53af269d1ab5)
2026-03-24 11:58:29.336 INFO:histserv:RPC<Flush> - flushed histogram to hist.h5 (hist_id=52c77c93da8146f2a72c53af269d1ab5)
```

Or check out how to use remote histogram filling with an example coffea Processor in `example/coffea_processor.py`.

## Current supported types

Axis support:
- `hist.axis.Regular`
- `hist.axis.Boolean`
- `hist.axis.Variable`
- `hist.axis.Integer`
- `hist.axis.IntCategory`
- `hist.axis.StrCategory`

`np.dtype` support for `hist.axis.{Regular,Variable,Integer}`:
- `np.float64`
- `np.float32`
- `np.int64`
- `np.int32`

## Developer Info

### Install
```shell
uv pip install -e . --group=dev
```

### Protobuf Codegen

```shell
python -m grpc_tools.protoc -Isrc/histserv/protos --python_out=src/histserv/protos --pyi_out=src/histserv/protos --grpc_python_out=src/histserv/protos src/histserv/protos/hist.proto
```
Maybe adjust imports in `src/histserv/protos/hist_pb2_grpc.py`.


<!--Badge URLs-->
[conda-badge]: https://img.shields.io/conda/vn/conda-forge/histserv
[conda-link]: https://github.com/conda-forge/histserv-feedstock
[pypi-link]: https://pypi.org/project/histserv/
[pypi-platforms]: https://img.shields.io/pypi/pyversions/histserv
[pypi-version]: https://badge.fury.io/py/histserv.svg

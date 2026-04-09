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

Start the async gRPC server (or just `./example/start_server.sh`):
```shell
histserv --port 50051
# 2026-03-26 11:58:00.643 INFO:histserv:server (listening at [::]:50051) started with port=50051, prune_after=24.00 h, prune_interval=5.00 min, stats_interval=5.00 s
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
    # fill the remote hist; the client pre-bins locally and sends dense storage
    H_remote.fill(x=np.random.normal(size=1000))
    # retrieve it back as a ChunkedHist, drop it from the server, and materialize it locally
    H_snapshot = H_remote.snapshot(delete_from_server=True)
    print(H_snapshot.to_hist())


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

## Dashboard

histserv includes an optional real-time observability dashboard.  It is a
read-only web UI that shows server health, lists live histograms, and renders
them as they are filled.

### Install the dashboard extra

```shell
pip install "histserv[dashboard]"
```

This pulls in FastAPI, uvicorn, and httpx alongside the base install.

### Start the server with the dashboard

Pass `--dashboard-port` to expose the observability interface:

```shell
histserv --port 50051 --dashboard-port 8050
```

Open [http://localhost:8050](http://localhost:8050) in a browser (once a
frontend bundle has been built; see below) or connect directly to the
WebSocket at `ws://localhost:8050/ws`.

The dashboard port exposes:

| Path | Description |
|------|-------------|
| `GET /api/histograms/{hist_id}/metadata` | Histogram metadata including chunk-axis categories |
| `GET /api/histograms/{hist_id}` | One-shot JSON snapshot of a selected dense chunk |
| `WS  /ws` | Subscription-based streaming protocol (primary) |
| `/*` | Serves the built Svelte frontend (production only) |

### WebSocket protocol

All messages share an envelope:

```json
{ "type": "string", "ts": 1712500000.123, "payload": { ... } }
```

**Client → server**

| type | payload | description |
|------|---------|-------------|
| `subscribe` | `{ "streams": ["stats", "hist_list"] }` | Periodic server stats and histogram list |
| `subscribe_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" }, "rate_limit_hz": 1 }` | Stream one dense chunk |
| `unsubscribe_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" } }` | Stop streaming one dense chunk |
| `get_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" } }` | One-shot dense chunk fetch |

**Server → client**

| type | description |
|------|-------------|
| `stats` | Server health (uptime, rpc counts, cpu, memory) — ~1 s |
| `hist_list` | Live histogram summaries, including current chunk-axis categories — ~2 s |
| `hist_meta` | One-shot dense histogram schema for a selected histogram |
| `hist_data` | Dense chunk payload (`selection`, `values`, `version`) |
| `error` | `{ "message": "…", "code": "NOT_FOUND" \| "INTERNAL" }` |

Dashboard histogram fetches always require a full chunk selection expressed as a
JSON object keyed by chunk-axis name. For histograms without chunk axes, the
selection is the empty object encoded as `{}`:

```text
/api/histograms/<hist_id>?selection=%7B%7D
```

## Examples

See `example/` for more examples.

Run example client:
```shell
python example/client.py
# Remote hist initialized: RemoteHist(hist_id='52c77c93da8146f2a72c53af269d1ab5', address='[::]:50051', token=None)
# Remote hist fill succeeded.
# Snapshotting current hist: ChunkedHist(...)
# Remote hist fill succeeded.
# Remote hist fill succeeded.
# Remote hist flushed successfully to hist.h5.
```

Or check out how to use remote histogram filling with an example coffea Processor in `example/coffea_processor.py`.

Useful client methods on `RemoteHist`:
- `fill(...)`
- `fill_many([...])`
- `snapshot(delete_from_server=False)`
- `reset()`
- `exists()`
- `get_connection_info()`
- `RemoteHist.from_connection_info(...)`
- `flush(destination="hist.h5")`
- `delete()`

## Current supported types

Axis support:
- `hist.axis.Regular` without transforms
- `hist.axis.Boolean`
- `hist.axis.Variable`
- `hist.axis.Integer`
- `hist.axis.IntCategory`
- `hist.axis.StrCategory`

Storage support:
- `hist.storage.Double`
- `hist.storage.Int64`
- `boost_histogram.storage.AtomicInt64`
- `hist.storage.Weight`
- `boost_histogram.storage.Unlimited`

Unsupported today:
- transformed `hist.axis.Regular`
- `boost_histogram.storage.Mean`
- `boost_histogram.storage.WeightedMean`

Notes:
- Growable categorical axes (`IntCategory`, `StrCategory`) are treated as
  chunk keys rather than dense axes.
- Histograms with one or more growable categorical axes are supported; the
  categorical values must be provided as scalars when filling.
- On the wire, fills are sent as dense per-chunk payloads rather than as
  generic Python objects.
- `RemoteHist.snapshot()` returns a `ChunkedHist`; call `.to_hist()` to
  materialize a local `hist.Hist`.
- `fill_many(...)` is useful for bundling several fills into one gRPC request.
- Dense ndarray transport is generic over NumPy dtypes, but object arrays are
  not supported on the wire.

## Developer Info

### Install
```shell
uv sync --dev
```

### Test
```shell
python -m pytest -q
uvx ty check src
```

### Protobuf Codegen

```shell
python -m grpc_tools.protoc -Isrc/histserv/protos --python_out=src/histserv/protos --pyi_out=src/histserv/protos --grpc_python_out=src/histserv/protos src/histserv/protos/hist.proto
```
After regeneration, ensure `src/histserv/protos/hist_pb2_grpc.py` keeps the
package-relative import:

```python
from . import hist_pb2 as hist__pb2
```


<!--Badge URLs-->
[conda-badge]: https://img.shields.io/conda/vn/conda-forge/histserv
[conda-link]: https://github.com/conda-forge/histserv-feedstock
[pypi-link]: https://pypi.org/project/histserv/
[pypi-platforms]: https://img.shields.io/pypi/pyversions/histserv
[pypi-version]: https://badge.fury.io/py/histserv.svg

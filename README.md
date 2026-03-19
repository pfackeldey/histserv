# Histogramming as a Service (HistServ)

## Install
```shell
uv pip install .
```

## Example

See `example/`.

Start gRPC server (or just `./example/start_server.sh`):
```shell
histserv --port 50051 --n-threads 4
# INFO:histserv:Histogram server started, listening on [::]:50051 with 4 threads
```

Run example client:
```shell
python example/client.py
# Remote hist initialized: RemoteHist<ID=eccd04e4b6e64523aae410ea0fe1f15f @[::]:50051>
# Histogram remote_hist received: success: true
#
# Snapshotting current hist: Hist(
#   Regular(10, -2, 2, name='x', label='X Axis'),
#   Regular(10, -2, 2, name='y', label='Y Axis'),
#   StrCategory(['data', 'drell-yan'], growth=True, name='dataset', label='Dataset'),
#  storage=Weight()) # Sum: WeightedSum(value=910974, variance=910974) (WeightedSum(value=1e+06, variance=1e+06) with flow)
#
# Histogram remote_hist received: success: true
#
# Histogram remote_hist received: success: true
#
# Histogram remote_hist received: Histogram (eccd04e4b6e64523aae410ea0fe1f15f) flushed successfully to hist.h5.
```

Or an example coffea Processor:
```shell
python example/coffea_processor.py
# All remote fills succeeded!
# Output hist: Hist(
#   Regular(10, -2, 2, name='x', label='X Axis'),
#   Regular(10, -2, 2, name='y', label='Y Axis'),
#   StrCategory(['data', 'drell-yan'], growth=True, name='dataset', label='Dataset'),
#   storage=Weight()) # Sum: WeightedSum(value=3.64502e+06, variance=3.64502e+06) (WeightedSum(value=4e+06, variance=4e+06) with flow)
```


And the server logs additionally (after running the client script):
```shell
# INFO:histserv:Initialized histogram (eccd04e4b6e64523aae410ea0fe1f15f)
# INFO:histserv:Filled histogram (eccd04e4b6e64523aae410ea0fe1f15f) with 24,000,000 bytes
# INFO:histserv:Filled histogram (eccd04e4b6e64523aae410ea0fe1f15f) with 24,000,000 bytes
# INFO:histserv:Filled histogram (eccd04e4b6e64523aae410ea0fe1f15f) with 24,000,000 bytes
# INFO:histserv:Flushed histogram (eccd04e4b6e64523aae410ea0fe1f15f) to hist.h5)
```

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

### protobuf codegen

```shell
python -m grpc_tools.protoc -Isrc/histserv/protos --python_out=src/histserv/protos --pyi_out=src/histserv/protos --grpc_python_out=src/histserv/protos src/histserv/protos/hist.proto
```
Maybe adjust imports in `src/histserv/protos/hist_pb2_grpc.py`.

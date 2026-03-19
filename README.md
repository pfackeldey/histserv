# Histogramming as a Service (HistServ)

[![PyPI version][pypi-version]][pypi-link]
[![Conda-Forge][conda-badge]][conda-link]
[![PyPI platforms][pypi-platforms]][pypi-link]

## Install PyPI
```shell
pip install histserv
```

## Install Conda-Forge
```shell
conda install -c conda-forge histserv
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
# Remote hist initialized: RemoteHist<ID=52c77c93da8146f2a72c53af269d1ab5 @[::]:50051>
# Remote hist filled successfully? -> True
# Snapshotting current hist: Hist(
#   Regular(10, -2, 2, name='x', label='X Axis'),
#   Regular(10, -2, 2, name='y', label='Y Axis'),
#   StrCategory(['data', 'drell-yan'], growth=True, name='dataset', label='Dataset'),
#   storage=Weight()) # Sum: WeightedSum(value=911503, variance=911503) (WeightedSum(value=1e+06, variance=1e+06) with flow)
# Remote hist filled successfully? -> True
# Remote hist filled successfully? -> True
# Remote hist flushed succesfully? -> Histogram (52c77c93da8146f2a72c53af269d1ab5) flushed successfully to hist.h5.
```

And the server logs additionally (after running the client script):
```shell
# INFO:histserv:Initialized histogram (52c77c93da8146f2a72c53af269d1ab5)
# INFO:histserv:Filled histogram (52c77c93da8146f2a72c53af269d1ab5) with 24,000,000 bytes
# INFO:histserv:Created snapshot of histogram (52c77c93da8146f2a72c53af269d1ab5)
# INFO:histserv:Filled histogram (52c77c93da8146f2a72c53af269d1ab5) with 24,000,000 bytes
# INFO:histserv:Filled histogram (52c77c93da8146f2a72c53af269d1ab5) with 24,000,000 bytes
# INFO:histserv:Flushed histogram (52c77c93da8146f2a72c53af269d1ab5) to hist.h5
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

from __future__ import annotations

import numpy as np
import pytest

from histserv.serialize import deserialize_nparray, serialize_nparray


@pytest.mark.parametrize(
    "dtype",
    [
        np.dtype(np.bool_),
        np.dtype(np.uint8),
        np.dtype(np.uint16),
        np.dtype(np.uint32),
        np.dtype(np.uint64),
        np.dtype(np.int8),
        np.dtype(np.int16),
        np.dtype(np.int32),
        np.dtype(np.int64),
        np.dtype(np.float32),
        np.dtype(np.float64),
    ],
)
def test_serialize_nparray_round_trips_generic_numpy_dtypes(dtype: np.dtype) -> None:
    array = np.arange(6, dtype=np.int64).astype(dtype, copy=False).reshape(2, 3)
    restored = deserialize_nparray(serialize_nparray(array))
    np.testing.assert_equal(restored, array)
    assert restored.dtype == array.dtype


def test_serialize_nparray_rejects_object_dtype() -> None:
    with pytest.raises(ValueError, match="object arrays are not supported"):
        serialize_nparray(np.array(["a", "b"], dtype=object))

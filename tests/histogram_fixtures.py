from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import boost_histogram as bh
import hist
import numpy as np


@dataclass(frozen=True)
class CategoricalHistCase:
    name: str
    hist_factory: Callable[[], hist.Hist]
    axis_names: tuple[str, ...]
    expected_axis_values: tuple[list[int | str], ...]
    fill_calls: tuple[dict[str, Any], ...]

    def make_hist(self) -> hist.Hist:
        return self.hist_factory()


def regular_hist() -> hist.Hist:
    return hist.Hist(
        hist.axis.Regular(8, 0, 4, name="x"),
    )


def categorical_hist_cases() -> tuple[CategoricalHistCase, ...]:
    return (
        CategoricalHistCase(
            name="int_category",
            hist_factory=lambda: hist.Hist(
                hist.axis.Regular(4, 0, 4, name="x"),
                hist.axis.IntCategory([], growth=True, name="cat"),
                storage=bh.storage.Weight(),
            ),
            axis_names=("cat",),
            expected_axis_values=([1, 2, 3],),
            fill_calls=(
                {
                    "x": np.array([0.5, 2.5], dtype=np.float64),
                    "cat": 1,
                    "weight": np.array([1.0, 0.5], dtype=np.float64),
                },
                {
                    "x": np.array([1.5], dtype=np.float64),
                    "cat": 2,
                    "weight": np.array([2.0], dtype=np.float64),
                },
                {
                    "x": np.array([3.5], dtype=np.float64),
                    "cat": 3,
                    "weight": np.array([4.0], dtype=np.float64),
                },
                {
                    "x": np.array([0.5], dtype=np.float64),
                    "cat": 2,
                    "weight": np.array([1.5], dtype=np.float64),
                },
            ),
        ),
        CategoricalHistCase(
            name="str_category",
            hist_factory=lambda: hist.Hist(
                hist.axis.Regular(4, 0, 4, name="x"),
                hist.axis.StrCategory([], growth=True, name="label"),
                storage=bh.storage.Weight(),
            ),
            axis_names=("label",),
            expected_axis_values=(["alpha", "beta", "gamma"],),
            fill_calls=(
                {
                    "x": np.array([0.5, 2.5], dtype=np.float64),
                    "label": "alpha",
                    "weight": np.array([1.0, 0.5], dtype=np.float64),
                },
                {
                    "x": np.array([1.5], dtype=np.float64),
                    "label": "beta",
                    "weight": np.array([2.0], dtype=np.float64),
                },
                {
                    "x": np.array([3.5], dtype=np.float64),
                    "label": "gamma",
                    "weight": np.array([4.0], dtype=np.float64),
                },
                {
                    "x": np.array([0.5], dtype=np.float64),
                    "label": "beta",
                    "weight": np.array([1.5], dtype=np.float64),
                },
            ),
        ),
        CategoricalHistCase(
            name="int_str_category_2d",
            hist_factory=lambda: hist.Hist(
                hist.axis.Regular(4, 0, 4, name="x"),
                hist.axis.IntCategory([], growth=True, name="cat"),
                hist.axis.StrCategory([], growth=True, name="label"),
                storage=bh.storage.Weight(),
            ),
            axis_names=("cat", "label"),
            expected_axis_values=([1, 2, 3], ["alpha", "beta", "gamma"]),
            fill_calls=(
                {
                    "x": np.array([0.5, 2.5], dtype=np.float64),
                    "cat": 1,
                    "label": "alpha",
                    "weight": np.array([1.0, 0.5], dtype=np.float64),
                },
                {
                    "x": np.array([1.5], dtype=np.float64),
                    "cat": 2,
                    "label": "beta",
                    "weight": np.array([2.0], dtype=np.float64),
                },
                {
                    "x": np.array([3.5], dtype=np.float64),
                    "cat": 3,
                    "label": "gamma",
                    "weight": np.array([4.0], dtype=np.float64),
                },
                {
                    "x": np.array([0.5], dtype=np.float64),
                    "cat": 2,
                    "label": "alpha",
                    "weight": np.array([1.5], dtype=np.float64),
                },
            ),
        ),
        CategoricalHistCase(
            name="str_category_3d",
            hist_factory=lambda: hist.Hist(
                hist.axis.Regular(4, 0, 4, name="x"),
                hist.axis.StrCategory([], growth=True, name="cat"),
                hist.axis.StrCategory([], growth=True, name="var"),
                hist.axis.StrCategory([], growth=True, name="region"),
                storage=bh.storage.Weight(),
            ),
            axis_names=("cat", "var", "region"),
            expected_axis_values=(
                ["alpha", "beta", "gamma"],
                ["u", "v", "w"],
                ["eu", "us", "apac"],
            ),
            fill_calls=(
                {
                    "x": np.array([0.5, 2.5], dtype=np.float64),
                    "cat": "alpha",
                    "var": "u",
                    "region": "eu",
                    "weight": np.array([1.0, 0.5], dtype=np.float64),
                },
                {
                    "x": np.array([1.5], dtype=np.float64),
                    "cat": "beta",
                    "var": "v",
                    "region": "us",
                    "weight": np.array([2.0], dtype=np.float64),
                },
                {
                    "x": np.array([3.5], dtype=np.float64),
                    "cat": "gamma",
                    "var": "w",
                    "region": "apac",
                    "weight": np.array([4.0], dtype=np.float64),
                },
                {
                    "x": np.array([0.5], dtype=np.float64),
                    "cat": "beta",
                    "var": "u",
                    "region": "eu",
                    "weight": np.array([1.5], dtype=np.float64),
                },
            ),
        ),
    )

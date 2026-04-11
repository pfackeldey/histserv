// Utilities for converting UHI axis metadata to the internal RenderAxis format
// and for trimming flow bins (underflow/overflow) from values arrays.
//
// UHI (Universal Histogram Interface) schema version 1 — see boost-histogram docs.

import type { UhiAxis, RenderAxis } from './types/protocol'

function axisName(axis: UhiAxis): string {
  return axis.metadata?.name ?? ''
}

function axisLabel(axis: UhiAxis): string {
  return axis.metadata?.label ?? axisName(axis)
}

/**
 * Convert a single UHI axis descriptor to the internal RenderAxis used by D3.
 *
 * For `regular` axes, edges are computed as:
 *   [lower, lower+step, lower+2*step, ..., upper]  (bins+1 values)
 *
 * For `variable` axes, edges are taken directly from the UHI payload.
 *
 * For categorical axes, categories become string labels.
 *
 * For `boolean` axes, labels are ['False', 'True'].
 */
export function uhiAxisToRenderAxis(axis: UhiAxis): RenderAxis {
  const name = axisName(axis)
  const label = axisLabel(axis)

  if (axis.type === 'regular') {
    // Compute bin edges from lower/upper/bins (bins+1 edge values)
    const { lower, upper, bins } = axis
    const step = (upper - lower) / bins
    const edges = Array.from({ length: bins + 1 }, (_, i) => lower + i * step)
    return { name, label, type: 'numeric', edges }
  }

  if (axis.type === 'variable') {
    return { name, label, type: 'numeric', edges: axis.edges }
  }

  if (axis.type === 'category_str') {
    return { name, label, type: 'categorical', labels: axis.categories }
  }

  if (axis.type === 'category_int') {
    return { name, label, type: 'categorical', labels: axis.categories.map(String) }
  }

  // boolean axis
  return { name, label, type: 'categorical', labels: ['False', 'True'] }
}

/**
 * Strip underflow and/or overflow bins from a 1D values array.
 *
 * For `regular`/`variable` axes: underflow is index 0, overflow is the last index.
 * For categorical/boolean axes: `flow: true` means there is one flow bin at each end.
 * For `boolean`: no flow bins.
 */
export function trimFlowBins1D(values: number[], axis: UhiAxis): number[] {
  let start = 0
  let end = values.length

  if (axis.type === 'regular' || axis.type === 'variable') {
    if (axis.underflow) start += 1
    if (axis.overflow) end -= 1
  } else if (axis.type === 'category_str' || axis.type === 'category_int') {
    if (axis.flow) {
      start += 1
      end -= 1
    }
  }
  // boolean: no flow bins

  return values.slice(start, end)
}

/**
 * Strip underflow/overflow from a 2D values array (array of rows, where each
 * row corresponds to one x-bin and each element corresponds to a y-bin).
 *
 * Shape: values[xi][yi]
 */
export function trimFlowBins2D(values: number[][], xAxis: UhiAxis, yAxis: UhiAxis): number[][] {
  // Trim x (outer array)
  let xStart = 0
  let xEnd = values.length
  if (xAxis.type === 'regular' || xAxis.type === 'variable') {
    if (xAxis.underflow) xStart += 1
    if (xAxis.overflow) xEnd -= 1
  } else if (xAxis.type === 'category_str' || xAxis.type === 'category_int') {
    if (xAxis.flow) {
      xStart += 1
      xEnd -= 1
    }
  }

  // Trim y (inner arrays) using 1D logic on each row
  return values.slice(xStart, xEnd).map((row) => trimFlowBins1D(row, yAxis))
}

import { describe, it, expect } from 'vitest'
import { uhiAxisToRenderAxis, trimFlowBins1D, trimFlowBins2D } from '../lib/uhi-axis'
import type { UhiAxis } from '../lib/types/protocol'

describe('uhiAxisToRenderAxis', () => {
  it('converts regular axis: edges computed from lower/upper/bins', () => {
    const axis: UhiAxis = {
      type: 'regular',
      lower: 0,
      upper: 3,
      bins: 3,
      underflow: true,
      overflow: true,
      circular: false,
      metadata: { name: 'x', label: 'x-axis' },
    }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.type).toBe('numeric')
    if (result.type === 'numeric') {
      expect(result.edges).toHaveLength(4) // bins+1
      expect(result.edges[0]).toBeCloseTo(0)
      expect(result.edges[3]).toBeCloseTo(3)
      expect(result.edges[1]).toBeCloseTo(1)
    }
    expect(result.name).toBe('x')
    expect(result.label).toBe('x-axis')
  })

  it('converts regular axis: edge step is (upper-lower)/bins', () => {
    const axis: UhiAxis = {
      type: 'regular',
      lower: -3,
      upper: 3,
      bins: 30,
      underflow: true,
      overflow: true,
      circular: false,
      metadata: { name: 'y', label: '' },
    }
    const result = uhiAxisToRenderAxis(axis)
    if (result.type === 'numeric') {
      expect(result.edges).toHaveLength(31)
      expect(result.edges[0]).toBeCloseTo(-3)
      expect(result.edges[30]).toBeCloseTo(3)
    }
  })

  it('converts variable axis: edges passed through', () => {
    const edges = [0.0, 1.0, 3.0, 6.0]
    const axis: UhiAxis = {
      type: 'variable',
      edges,
      underflow: true,
      overflow: true,
      circular: false,
      metadata: { name: 'pt' },
    }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.type).toBe('numeric')
    if (result.type === 'numeric') {
      expect(result.edges).toEqual(edges)
    }
    expect(result.name).toBe('pt')
  })

  it('converts category_str axis: categories become string labels', () => {
    const axis: UhiAxis = {
      type: 'category_str',
      categories: ['data', 'mc', 'signal'],
      flow: false,
      metadata: { name: 'dataset', label: 'Dataset' },
    }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.type).toBe('categorical')
    if (result.type === 'categorical') {
      expect(result.labels).toEqual(['data', 'mc', 'signal'])
    }
    expect(result.label).toBe('Dataset')
  })

  it('converts category_int axis: integer categories become string labels', () => {
    const axis: UhiAxis = {
      type: 'category_int',
      categories: [10, 20, 30],
      flow: false,
      metadata: { name: 'run' },
    }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.type).toBe('categorical')
    if (result.type === 'categorical') {
      expect(result.labels).toEqual(['10', '20', '30'])
    }
  })

  it('converts boolean axis: labels are False/True', () => {
    const axis: UhiAxis = {
      type: 'boolean',
      metadata: { name: 'pass' },
    }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.type).toBe('categorical')
    if (result.type === 'categorical') {
      expect(result.labels).toEqual(['False', 'True'])
    }
  })

  it('uses empty string for name/label when metadata is missing', () => {
    const axis: UhiAxis = { type: 'boolean' }
    const result = uhiAxisToRenderAxis(axis)
    expect(result.name).toBe('')
    expect(result.label).toBe('')
  })
})

describe('trimFlowBins1D', () => {
  it('trims underflow and overflow for regular axis', () => {
    // 32 values: [underflow, 30 bins..., overflow]
    const values = [999, ...Array.from({ length: 30 }, (_, i) => i), 999]
    const axis: UhiAxis = {
      type: 'regular',
      lower: -3,
      upper: 3,
      bins: 30,
      underflow: true,
      overflow: true,
      circular: false,
    }
    const result = trimFlowBins1D(values, axis)
    expect(result).toHaveLength(30)
    expect(result[0]).toBe(0)
    expect(result[29]).toBe(29)
  })

  it('trims only underflow when overflow=false', () => {
    const values = [999, 1, 2, 3]
    const axis: UhiAxis = {
      type: 'regular',
      lower: 0,
      upper: 3,
      bins: 3,
      underflow: true,
      overflow: false,
      circular: false,
    }
    const result = trimFlowBins1D(values, axis)
    expect(result).toEqual([1, 2, 3])
  })

  it('trims only overflow when underflow=false', () => {
    const values = [1, 2, 3, 999]
    const axis: UhiAxis = {
      type: 'regular',
      lower: 0,
      upper: 3,
      bins: 3,
      underflow: false,
      overflow: true,
      circular: false,
    }
    const result = trimFlowBins1D(values, axis)
    expect(result).toEqual([1, 2, 3])
  })

  it('trims flow bins for category_str axis with flow=true', () => {
    const values = [999, 10, 20, 999]
    const axis: UhiAxis = {
      type: 'category_str',
      categories: ['a', 'b'],
      flow: true,
    }
    const result = trimFlowBins1D(values, axis)
    expect(result).toEqual([10, 20])
  })

  it('does not trim for category_str axis with flow=false', () => {
    const values = [10, 20]
    const axis: UhiAxis = {
      type: 'category_str',
      categories: ['a', 'b'],
      flow: false,
    }
    const result = trimFlowBins1D(values, axis)
    expect(result).toEqual([10, 20])
  })

  it('does not trim for boolean axis', () => {
    const values = [5, 10]
    const axis: UhiAxis = { type: 'boolean' }
    const result = trimFlowBins1D(values, axis)
    expect(result).toEqual([5, 10])
  })
})

describe('trimFlowBins2D', () => {
  it('trims underflow and overflow in both dimensions', () => {
    // 4x4: [underflow_x[underflow_y, y0, y1, overflow_y], x0[...], x1[...], overflow_x[...]]
    const values = [
      [0, 0, 0, 0], // underflow x row
      [0, 1, 2, 0], // x=0 row
      [0, 3, 4, 0], // x=1 row
      [0, 0, 0, 0], // overflow x row
    ]
    const xAxis: UhiAxis = {
      type: 'regular',
      lower: 0,
      upper: 2,
      bins: 2,
      underflow: true,
      overflow: true,
      circular: false,
    }
    const yAxis: UhiAxis = {
      type: 'regular',
      lower: 0,
      upper: 2,
      bins: 2,
      underflow: true,
      overflow: true,
      circular: false,
    }
    const result = trimFlowBins2D(values, xAxis, yAxis)
    expect(result).toEqual([
      [1, 2],
      [3, 4],
    ])
  })
})

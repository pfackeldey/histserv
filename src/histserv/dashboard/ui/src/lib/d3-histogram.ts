import * as d3 from 'd3'
import type { HistDataPayload, HistMetaPayload, RenderAxis } from './types/protocol'
import { uhiAxisToRenderAxis, trimFlowBins1D, trimFlowBins2D } from './uhi-axis'

const TRANSITION_MS = 350
const EASE = d3.easeCubicOut

// Flatten nested arrays to 1D (for 2D+ histograms, used by heatmap)
function flatten(values: number | number[] | number[][]): number[] {
  if (typeof values === 'number') return [values]
  if (typeof values[0] === 'number') return values as number[]
  return (values as number[][]).flat()
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function getOrCreateTooltip(): d3.Selection<HTMLDivElement, unknown, HTMLElement, unknown> {
  const existing = d3.select<HTMLDivElement, unknown>('#hist-tooltip')
  if (!existing.empty()) return existing
  return d3
    .select('body')
    .append('div')
    .attr('id', 'hist-tooltip')
    .style('position', 'fixed')
    .style('pointer-events', 'none')
    .style('opacity', '0')
    .style('background', 'rgba(10,10,20,0.92)')
    .style('border', '1px solid rgba(100,160,255,0.3)')
    .style('border-radius', '4px')
    .style('padding', '6px 10px')
    .style('font-family', '"JetBrains Mono", "Fira Mono", monospace')
    .style('font-size', '11px')
    .style('line-height', '1.6')
    .style('color', '#e0e8ff')
    .style('backdrop-filter', 'blur(4px)')
    .style('box-shadow', '0 4px 20px rgba(0,0,0,0.5)')
    .style('z-index', '9999')
    .style('white-space', 'nowrap')
    .style('transition', 'opacity 0.12s ease')
}

export function showTooltip(html: string, event: MouseEvent) {
  const tt = getOrCreateTooltip()
  tt.html(html).style('opacity', '1')
  positionTooltip(tt, event)
}

export function moveTooltip(event: MouseEvent) {
  positionTooltip(getOrCreateTooltip(), event)
}

export function hideTooltip() {
  getOrCreateTooltip().style('opacity', '0')
}

function positionTooltip(
  tt: d3.Selection<HTMLDivElement, unknown, HTMLElement, unknown>,
  event: MouseEvent,
) {
  const margin = 14
  const node = tt.node()!
  const { clientX: x, clientY: y } = event
  const { innerWidth: vw, innerHeight: vh } = window
  const w = node.offsetWidth
  const h = node.offsetHeight
  const left = x + margin + w > vw ? x - w - margin : x + margin
  const top = y + margin + h > vh ? y - h - margin : y + margin
  tt.style('left', `${left}px`).style('top', `${top}px`)
}

// ─── Axis styling helpers ─────────────────────────────────────────────────────

export function styleAxis(g: d3.Selection<SVGGElement, unknown, null, undefined>) {
  g.selectAll('.domain').attr('stroke', 'rgba(255,255,255,0.15)')
  g.selectAll('.tick line').attr('stroke', 'rgba(255,255,255,0.15)')
  g.selectAll('.tick text')
    .attr('fill', 'rgba(200,210,240,0.7)')
    .attr('font-family', '"JetBrains Mono", "Fira Mono", monospace')
    .attr('font-size', '10px')
}

// ─── Gridlines ────────────────────────────────────────────────────────────────

function addGridlines(
  svg: d3.Selection<SVGGElement, unknown, null, undefined>,
  yScale: d3.ScaleLinear<number, number>,
  w: number,
) {
  svg
    .append('g')
    .attr('class', 'grid')
    .call(
      d3
        .axisLeft(yScale)
        .ticks(5)
        .tickSize(-w)
        .tickFormat(() => ''),
    )
    .call((g) => {
      g.selectAll('.domain').remove()
      g.selectAll('.tick line')
        .attr('stroke', 'rgba(255,255,255,0.06)')
        .attr('stroke-dasharray', '3,3')
    })
}

// ─── 1D bar chart ─────────────────────────────────────────────────────────────

// Initialise the SVG skeleton once. Subsequent calls just update data.
function ensureSkeleton1D(container: SVGSVGElement) {
  const sel = d3.select(container)
  if (!sel.select('g.root').empty()) return
  const margin = { top: 20, right: 20, bottom: 44, left: 60 }
  const width = container.clientWidth || 480
  const height = container.clientHeight || 260
  sel.attr('viewBox', `0 0 ${width} ${height}`)

  const root = sel
    .append('g')
    .attr('class', 'root')
    .attr('transform', `translate(${margin.left},${margin.top})`)
  root.append('g').attr('class', 'grid')
  root.append('g').attr('class', 'bars')
  root
    .append('g')
    .attr('class', 'x-axis')
    .attr('transform', `translate(0,${height - margin.top - margin.bottom})`)
  root.append('g').attr('class', 'y-axis')
  root.append('text').attr('class', 'x-label')
  root.append('text').attr('class', 'y-label')
}

export function render1D(container: SVGSVGElement, values: number[], axis: RenderAxis) {
  ensureSkeleton1D(container)

  const margin = { top: 20, right: 20, bottom: 44, left: 60 }
  const width = container.clientWidth || 480
  const height = container.clientHeight || 260
  const w = width - margin.left - margin.right
  const h = height - margin.top - margin.bottom

  const isCategorical = axis.type === 'categorical'
  const labels = isCategorical ? axis.labels : null
  const edges = !isCategorical ? axis.edges : null

  // Build bar descriptors. Each bar carries enough info for the tooltip.
  type Bar = {
    key: string
    x0: number
    x1: number
    xPx: number
    wPx: number
    value: number
    binLabel: string
  }
  let bars: Bar[]
  let xScale: d3.ScaleBand<string> | d3.ScaleLinear<number, number>

  if (labels) {
    const scale = d3.scaleBand<string>().domain(labels).range([0, w]).padding(0.08)
    xScale = scale
    bars = labels.map((lbl, i) => ({
      key: lbl,
      x0: i,
      x1: i + 1,
      xPx: scale(lbl)!,
      wPx: scale.bandwidth(),
      value: values[i] ?? 0,
      binLabel: lbl,
    }))
  } else {
    const scale = d3
      .scaleLinear()
      .domain([edges![0], edges![edges!.length - 1]])
      .range([0, w])
    xScale = scale
    bars = values.map((v, i) => ({
      key: String(i),
      x0: edges![i],
      x1: edges![i + 1],
      xPx: scale(edges![i]),
      wPx: Math.max(0, scale(edges![i + 1]) - scale(edges![i]) - 0.5), // 0.5px gap
      value: v,
      binLabel: `[${fmtNum(edges![i])}, ${fmtNum(edges![i + 1])})`,
    }))
  }

  const maxVal = d3.max(values) ?? 0
  const yScale = d3
    .scaleLinear()
    .domain([0, maxVal * 1.08 || 1])
    .range([h, 0])
    .nice()
  const t = d3.transition().duration(TRANSITION_MS).ease(EASE)

  const svg = d3.select(container)
  const root = svg.select<SVGGElement>('g.root')

  // Gridlines (redraw — cheap)
  root.select('g.grid').remove()
  const grid = root.insert('g', ':first-child').attr('class', 'grid')
  addGridlines(grid, yScale, w)

  // Bars — D3 join with transition
  const barFill = (v: number) => {
    const ratio = maxVal > 0 ? v / maxVal : 0
    // Interpolate from a cool mid-blue to a bright accent
    return d3.interpolateRgb('#1e4a8a', '#60aaff')(ratio)
  }

  root
    .select<SVGGElement>('g.bars')
    .selectAll<SVGRectElement, Bar>('rect')
    .data(bars, (d) => d.key)
    .join(
      (enter) =>
        enter
          .append('rect')
          .attr('rx', 1)
          .attr('x', (d) => d.xPx)
          .attr('width', (d) => d.wPx)
          .attr('y', h)
          .attr('height', 0)
          .attr('fill', (d) => barFill(d.value))
          .attr('opacity', 0.9),
      (update) => update,
      (exit) => exit.transition(t).attr('y', h).attr('height', 0).remove(),
    )
    .on('mouseover', function (event: MouseEvent, d: Bar) {
      d3.select(this)
        .transition()
        .duration(80)
        .attr('opacity', 1)
        .attr('filter', 'brightness(1.25)')
      showTooltip(
        `<span style="color:#60aaff;font-weight:700">${fmtCount(d.value)}</span> counts<br>` +
          `<span style="color:#7090b0">bin: ${d.binLabel}</span>`,
        event,
      )
    })
    .on('mousemove', (event: MouseEvent) => moveTooltip(event))
    .on('mouseout', function () {
      d3.select(this).transition().duration(120).attr('opacity', 0.9).attr('filter', null)
      hideTooltip()
    })
    .transition(t)
    .attr('x', (d) => d.xPx)
    .attr('width', (d) => d.wPx)
    .attr('y', (d) => yScale(d.value))
    .attr('height', (d) => h - yScale(d.value))
    .attr('fill', (d) => barFill(d.value))

  // X axis
  const xAxisG = root.select<SVGGElement>('g.x-axis')
  if (labels) {
    xAxisG.transition(t).call(d3.axisBottom(xScale as d3.ScaleBand<string>))
  } else {
    xAxisG.transition(t).call(d3.axisBottom(xScale as d3.ScaleLinear<number, number>).ticks(6))
  }
  styleAxis(xAxisG)

  // Y axis
  const yAxisG = root.select<SVGGElement>('g.y-axis')
  yAxisG.transition(t).call(
    d3
      .axisLeft(yScale)
      .ticks(5)
      .tickFormat((v) => fmtCount(v as number)),
  )
  styleAxis(yAxisG)

  // Axis labels
  const xLbl = axis.label || axis.name
  root
    .select('text.x-label')
    .attr('x', w / 2)
    .attr('y', h + margin.bottom - 6)
    .attr('text-anchor', 'middle')
    .attr('fill', 'rgba(180,200,240,0.55)')
    .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
    .attr('font-size', '11px')
    .attr('letter-spacing', '0.04em')
    .text(xLbl)

  root
    .select('text.y-label')
    .attr('transform', 'rotate(-90)')
    .attr('x', -h / 2)
    .attr('y', -margin.left + 14)
    .attr('text-anchor', 'middle')
    .attr('fill', 'rgba(180,200,240,0.55)')
    .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
    .attr('font-size', '11px')
    .attr('letter-spacing', '0.04em')
    .text('counts')
}

// ─── 2D heatmap ───────────────────────────────────────────────────────────────

function ensureSkeleton2D(container: SVGSVGElement) {
  const sel = d3.select(container)
  if (!sel.select('g.root').empty()) return
  const margin = { top: 20, right: 72, bottom: 48, left: 60 }
  const width = container.clientWidth || 480
  const height = container.clientHeight || 340
  sel.attr('viewBox', `0 0 ${width} ${height}`)
  const root = sel
    .append('g')
    .attr('class', 'root')
    .attr('transform', `translate(${margin.left},${margin.top})`)
  root.append('g').attr('class', 'cells')
  root.append('g').attr('class', 'x-axis')
  root.append('g').attr('class', 'y-axis')
  root.append('text').attr('class', 'x-label')
  root.append('text').attr('class', 'y-label')
  // Colorbar group
  const cb = root.append('g').attr('class', 'colorbar')
  cb.append('defs')
    .append('linearGradient')
    .attr('id', 'cb-grad')
    .attr('x1', '0%')
    .attr('x2', '0%')
    .attr('y1', '100%')
    .attr('y2', '0%')
  cb.append('rect').attr('class', 'cb-rect')
  cb.append('g').attr('class', 'cb-axis')
}

export function render2D(
  container: SVGSVGElement,
  values: number[][],
  xAxis: RenderAxis,
  yAxis: RenderAxis,
) {
  ensureSkeleton2D(container)

  const margin = { top: 20, right: 72, bottom: 48, left: 60 }
  const width = container.clientWidth || 480
  const height = container.clientHeight || 340
  const w = width - margin.left - margin.right
  const h = height - margin.top - margin.bottom

  const nx = values.length
  const ny = values[0]?.length ?? 0

  const allVals = flatten(values)
  const maxVal = d3.max(allVals) ?? 1
  const colorScale = d3.scaleSequential(d3.interpolateInferno).domain([0, maxVal])

  const t = d3.transition().duration(TRANSITION_MS).ease(EASE)

  const cellW = w / nx
  const cellH = h / ny

  // X/Y scales for positioning
  const xEdges = xAxis.type === 'numeric' ? xAxis.edges : null
  const yEdges = yAxis.type === 'numeric' ? yAxis.edges : null
  const xLabels = xAxis.type === 'categorical' ? xAxis.labels : null
  const yLabels = yAxis.type === 'categorical' ? yAxis.labels : null

  const xTickScale = xEdges
    ? d3.scaleLinear().domain([xEdges[0], xEdges[nx]]).range([0, w])
    : d3
        .scaleBand<string>()
        .domain(xLabels ?? [])
        .range([0, w])

  const yTickScale = yEdges
    ? d3.scaleLinear().domain([yEdges[0], yEdges[ny]]).range([h, 0])
    : d3
        .scaleBand<string>()
        .domain(yLabels ?? [])
        .range([h, 0])

  // Build flat cell array for D3 join
  type Cell = { key: string; xi: number; yi: number; value: number; xLabel: string; yLabel: string }
  const cells: Cell[] = []
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < ny; j++) {
      cells.push({
        key: `${i}-${j}`,
        xi: i,
        yi: j,
        value: values[i][j],
        xLabel: xEdges
          ? `[${fmtNum(xEdges[i])}, ${fmtNum(xEdges[i + 1])})`
          : String(xLabels?.[i] ?? i),
        yLabel: yEdges
          ? `[${fmtNum(yEdges[j])}, ${fmtNum(yEdges[j + 1])})`
          : String(yLabels?.[j] ?? j),
      })
    }
  }

  const svg = d3.select(container)
  const root = svg.select<SVGGElement>('g.root')

  root
    .select<SVGGElement>('g.cells')
    .selectAll<SVGRectElement, Cell>('rect')
    .data(cells, (d) => d.key)
    .join(
      (enter) =>
        enter
          .append('rect')
          .attr('x', (d) => d.xi * cellW)
          .attr('y', (d) => h - (d.yi + 1) * cellH)
          .attr('width', cellW)
          .attr('height', cellH)
          .attr('fill', (d) => colorScale(d.value))
          .attr('opacity', 0),
      (update) => update,
      (exit) => exit.transition(t).attr('opacity', 0).remove(),
    )
    .on('mouseover', function (event: MouseEvent, d: Cell) {
      d3.select(this)
        .attr('stroke', 'rgba(255,255,255,0.6)')
        .attr('stroke-width', '1')
        .attr('filter', 'brightness(1.3)')
      showTooltip(
        `<span style="color:#f0a060;font-weight:700">${fmtCount(d.value)}</span> counts<br>` +
          `<span style="color:#7090b0">x: ${d.xLabel}</span><br>` +
          `<span style="color:#7090b0">y: ${d.yLabel}</span>`,
        event,
      )
    })
    .on('mousemove', (event: MouseEvent) => moveTooltip(event))
    .on('mouseout', function () {
      d3.select(this).attr('stroke', null).attr('stroke-width', null).attr('filter', null)
      hideTooltip()
    })
    .transition(t)
    .attr('x', (d) => d.xi * cellW)
    .attr('y', (d) => h - (d.yi + 1) * cellH)
    .attr('width', cellW)
    .attr('height', cellH)
    .attr('fill', (d) => colorScale(d.value))
    .attr('opacity', 1)

  // Axes
  const xAxisG = root.select<SVGGElement>('g.x-axis').attr('transform', `translate(0,${h})`)
  xAxisG.transition(t).call(d3.axisBottom(xTickScale as d3.AxisScale<d3.AxisDomain>).ticks(5))
  styleAxis(xAxisG)

  const yAxisG = root.select<SVGGElement>('g.y-axis')
  yAxisG.transition(t).call(d3.axisLeft(yTickScale as d3.AxisScale<d3.AxisDomain>).ticks(5))
  styleAxis(yAxisG)

  root
    .select('text.x-label')
    .attr('x', w / 2)
    .attr('y', h + margin.bottom - 6)
    .attr('text-anchor', 'middle')
    .attr('fill', 'rgba(180,200,240,0.55)')
    .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
    .attr('font-size', '11px')
    .attr('letter-spacing', '0.04em')
    .text(xAxis.label || xAxis.name)

  root
    .select('text.y-label')
    .attr('transform', 'rotate(-90)')
    .attr('x', -h / 2)
    .attr('y', -margin.left + 14)
    .attr('text-anchor', 'middle')
    .attr('fill', 'rgba(180,200,240,0.55)')
    .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
    .attr('font-size', '11px')
    .attr('letter-spacing', '0.04em')
    .text(yAxis.label || yAxis.name)

  // Colorbar
  const cbX = w + 12
  const cbW = 10

  const grad = root.select('defs #cb-grad')
  d3.range(11).forEach((i) => {
    const tVal = i / 10
    const stop = grad.select(`stop:nth-child(${i + 1})`)
    if (stop.empty()) {
      grad
        .append('stop')
        .attr('offset', `${tVal * 100}%`)
        .attr('stop-color', colorScale(tVal * maxVal))
    } else {
      stop.attr('stop-color', colorScale(tVal * maxVal))
    }
  })

  root
    .select('rect.cb-rect')
    .attr('x', cbX)
    .attr('y', 0)
    .attr('width', cbW)
    .attr('height', h)
    .style('fill', 'url(#cb-grad)')

  const cbScale = d3.scaleLinear().domain([0, maxVal]).range([h, 0])
  const cbAxisG = root
    .select<SVGGElement>('g.cb-axis')
    .attr('transform', `translate(${cbX + cbW},0)`)
  cbAxisG.transition(t).call(
    d3
      .axisRight(cbScale)
      .ticks(4)
      .tickFormat((v) => fmtCount(v as number)),
  )
  styleAxis(cbAxisG)
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  // Compact: avoid excessive decimals
  if (Number.isInteger(v)) return String(v)
  const s = v.toPrecision(4)
  return parseFloat(s).toString()
}

function fmtCount(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}k`
  return String(Math.round(v))
}

// ─── Entry point ──────────────────────────────────────────────────────────────

export function renderHistogram(
  container: SVGSVGElement,
  data: HistDataPayload,
  meta: HistMetaPayload,
) {
  const uhiAxes = meta.dense_metadata.axes
  const renderAxes = uhiAxes.map(uhiAxisToRenderAxis)

  if (renderAxes.length === 1) {
    const trimmed = trimFlowBins1D(data.values as number[], uhiAxes[0])
    render1D(container, trimmed, renderAxes[0])
  } else if (renderAxes.length === 2) {
    const trimmed = trimFlowBins2D(data.values as number[][], uhiAxes[0], uhiAxes[1])
    render2D(container, trimmed, renderAxes[0], renderAxes[1])
  }
  // 3D+ histograms: not yet supported
}

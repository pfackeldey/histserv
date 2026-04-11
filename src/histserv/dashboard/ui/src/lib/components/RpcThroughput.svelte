<script lang="ts">
  import * as d3 from 'd3'
  import { statsHistory } from '../stores/stats'
  import { styleAxis, showTooltip, hideTooltip } from '../d3-histogram'

  let container: SVGSVGElement

  const MARGIN = { top: 8, right: 16, bottom: 32, left: 52 }
  const TRANSITION_MS = 200

  const totalCalls = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0)

  // Compute per-second deltas between consecutive history points
  function deltas(history: typeof $statsHistory): { t: number; rate: number }[] {
    const result: { t: number; rate: number }[] = []
    for (let i = 1; i < history.length; i++) {
      const dt = history[i].observed_at - history[i - 1].observed_at
      if (dt <= 0) continue
      const dCalls =
        totalCalls(history[i].rpc_calls_total) - totalCalls(history[i - 1].rpc_calls_total)
      result.push({ t: history[i].observed_at, rate: dCalls / dt })
    }
    return result
  }

  $: pts = deltas($statsHistory)
  $: if (container && pts.length > 1) draw(pts)

  function ensureSkeleton(width: number, height: number) {
    const sel = d3.select(container)
    if (!sel.select('g.root').empty()) return
    sel.attr('viewBox', `0 0 ${width} ${height}`)
    const root = sel
      .append('g')
      .attr('class', 'root')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)
    root
      .append('path')
      .attr('class', 'line-path')
      .attr('fill', 'none')
      .attr('stroke', '#60aaff')
      .attr('stroke-width', '1.5')
    root.append('g').attr('class', 'x-axis')
    root.append('g').attr('class', 'y-axis')
    root.append('text').attr('class', 'y-label')
    // Crosshair (hidden until hover)
    root
      .append('line')
      .attr('class', 'crosshair')
      .attr('stroke', 'rgba(255,255,255,0.3)')
      .attr('stroke-dasharray', '3,3')
      .attr('pointer-events', 'none')
      .attr('opacity', '0')
    // Transparent overlay captures mouse events (appended last = on top)
    root.append('rect').attr('class', 'overlay').attr('fill', 'none').attr('pointer-events', 'all')
  }

  function draw(pts: { t: number; rate: number }[]) {
    const width = container.clientWidth || 320
    const height = container.clientHeight || 160
    ensureSkeleton(width, height)

    const w = width - MARGIN.left - MARGIN.right
    const h = height - MARGIN.top - MARGIN.bottom

    const xScale = d3
      .scaleLinear()
      .domain(d3.extent(pts, (d) => d.t) as [number, number])
      .range([0, w])
    const yScale = d3
      .scaleLinear()
      .domain([0, (d3.max(pts, (d) => d.rate) ?? 1) * 1.1])
      .range([h, 0])
      .nice()

    const lineGen = d3
      .line<{ t: number; rate: number }>()
      .x((d) => xScale(d.t))
      .y((d) => yScale(d.rate))
      .curve(d3.curveMonotoneX)

    const tr = d3.transition().duration(TRANSITION_MS).ease(d3.easeCubicOut)
    const root = d3.select(container).select<SVGGElement>('g.root')

    // Update line path (direct set — interpolating path strings looks wrong on rolling data)
    root.select<SVGPathElement>('path.line-path').attr('d', lineGen(pts))

    // Axes
    const xAxisG = root.select<SVGGElement>('g.x-axis').attr('transform', `translate(0,${h})`)
    xAxisG.transition(tr).call(
      d3
        .axisBottom(xScale)
        .ticks(5)
        .tickFormat((d) => {
          const date = new Date((d as number) * 1000)
          return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
        }),
    )
    styleAxis(xAxisG)

    const yAxisG = root.select<SVGGElement>('g.y-axis')
    yAxisG.transition(tr).call(d3.axisLeft(yScale).ticks(4))
    styleAxis(yAxisG)

    root
      .select('text.y-label')
      .attr('transform', 'rotate(-90)')
      .attr('x', -h / 2)
      .attr('y', -MARGIN.left + 12)
      .attr('text-anchor', 'middle')
      .attr('fill', 'rgba(180,200,240,0.55)')
      .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
      .attr('font-size', '11px')
      .text('RPCs/s')

    // Crosshair bisection hover
    const crosshair = root.select<SVGLineElement>('line.crosshair')
    const times = pts.map((p) => p.t)
    root
      .select<SVGRectElement>('rect.overlay')
      .attr('x', 0)
      .attr('y', 0)
      .attr('width', w)
      .attr('height', h)
      .on('mousemove', function (event: MouseEvent) {
        const [mx] = d3.pointer(event)
        const tVal = xScale.invert(mx)
        const idx = Math.min(d3.bisectLeft(times, tVal), pts.length - 1)
        const pt = pts[idx]
        crosshair
          .attr('x1', xScale(pt.t))
          .attr('x2', xScale(pt.t))
          .attr('y1', 0)
          .attr('y2', h)
          .attr('opacity', '1')
        const date = new Date(pt.t * 1000)
        const timeStr = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
        showTooltip(
          `<span style="color:#60aaff;font-weight:700">${pt.rate.toFixed(2)}</span> RPCs/s<br>` +
            `<span style="color:#7090b0">${timeStr}</span>`,
          event,
        )
      })
      .on('mouseleave', function () {
        crosshair.attr('opacity', '0')
        hideTooltip()
      })
  }
</script>

<section>
  <h3>RPC Throughput</h3>
  <svg bind:this={container} style="width:100%;height:160px"></svg>
</section>

<style>
  section {
    padding: 0.5rem 1rem;
  }
  h3 {
    margin: 0 0 0.5rem;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-muted, #888);
  }
</style>

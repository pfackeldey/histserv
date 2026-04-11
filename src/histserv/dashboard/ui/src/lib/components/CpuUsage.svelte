<script lang="ts">
  import * as d3 from 'd3'
  import { statsHistory } from '../stores/stats'
  import { styleAxis, showTooltip, hideTooltip } from '../d3-histogram'

  let container: SVGSVGElement

  const MARGIN = { top: 8, right: 16, bottom: 32, left: 52 }
  const TRANSITION_MS = 200
  const COLOR_USER = '#4e9af1'
  const COLOR_SYS = '#e07b54'

  function cpuDeltas(history: typeof $statsHistory): { t: number; user: number; sys: number }[] {
    const result: { t: number; user: number; sys: number }[] = []
    for (let i = 1; i < history.length; i++) {
      const dt = history[i].observed_at - history[i - 1].observed_at
      if (dt <= 0) continue
      result.push({
        t: history[i].observed_at,
        user: (history[i].cpu_user - history[i - 1].cpu_user) / dt,
        sys: (history[i].cpu_system - history[i - 1].cpu_system) / dt,
      })
    }
    return result
  }

  $: pts = cpuDeltas($statsHistory)
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
      .attr('class', 'line-user')
      .attr('fill', 'none')
      .attr('stroke', COLOR_USER)
      .attr('stroke-width', '1.5')
    root
      .append('path')
      .attr('class', 'line-sys')
      .attr('fill', 'none')
      .attr('stroke', COLOR_SYS)
      .attr('stroke-width', '1.5')
    root.append('g').attr('class', 'x-axis')
    root.append('g').attr('class', 'y-axis')
    root.append('text').attr('class', 'y-label')
    // Legend (static — created once)
    const legend = root.append('g').attr('class', 'legend')
    legend.append('circle').attr('r', 4).attr('fill', COLOR_USER)
    legend
      .append('text')
      .attr('x', 8)
      .attr('dy', '0.35em')
      .attr('fill', 'rgba(200,210,240,0.7)')
      .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
      .attr('font-size', '10px')
      .text('user')
    legend.append('circle').attr('cx', 44).attr('r', 4).attr('fill', COLOR_SYS)
    legend
      .append('text')
      .attr('x', 52)
      .attr('dy', '0.35em')
      .attr('fill', 'rgba(200,210,240,0.7)')
      .attr('font-family', '"JetBrains Mono","Fira Mono",monospace')
      .attr('font-size', '10px')
      .text('sys')
    // Crosshair + overlay
    root
      .append('line')
      .attr('class', 'crosshair')
      .attr('stroke', 'rgba(255,255,255,0.3)')
      .attr('stroke-dasharray', '3,3')
      .attr('pointer-events', 'none')
      .attr('opacity', '0')
    root.append('rect').attr('class', 'overlay').attr('fill', 'none').attr('pointer-events', 'all')
  }

  function draw(pts: { t: number; user: number; sys: number }[]) {
    const width = container.clientWidth || 320
    const height = container.clientHeight || 160
    ensureSkeleton(width, height)

    const w = width - MARGIN.left - MARGIN.right
    const h = height - MARGIN.top - MARGIN.bottom

    const xScale = d3
      .scaleLinear()
      .domain(d3.extent(pts, (d) => d.t) as [number, number])
      .range([0, w])
    const maxVal = Math.max(d3.max(pts, (d) => d.user + d.sys) ?? 0, 0.01)
    const yScale = d3
      .scaleLinear()
      .domain([0, maxVal * 1.1])
      .range([h, 0])
      .nice()

    const lineUser = d3
      .line<{ t: number; user: number; sys: number }>()
      .x((d) => xScale(d.t))
      .y((d) => yScale(d.user))
      .curve(d3.curveMonotoneX)
    const lineSys = d3
      .line<{ t: number; user: number; sys: number }>()
      .x((d) => xScale(d.t))
      .y((d) => yScale(d.sys))
      .curve(d3.curveMonotoneX)

    const tr = d3.transition().duration(TRANSITION_MS).ease(d3.easeCubicOut)
    const root = d3.select(container).select<SVGGElement>('g.root')

    // Update paths directly (interpolating path strings on rolling time-series looks wrong)
    root.select<SVGPathElement>('path.line-user').attr('d', lineUser(pts))
    root.select<SVGPathElement>('path.line-sys').attr('d', lineSys(pts))

    // Position legend in top-right
    root.select('g.legend').attr('transform', `translate(${w - 100}, 4)`)

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
      .text('CPU (s/s)')

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
          `<span style="color:${COLOR_USER};font-weight:700">${pt.user.toFixed(3)}</span> user&nbsp;&nbsp;` +
            `<span style="color:${COLOR_SYS};font-weight:700">${pt.sys.toFixed(3)}</span> sys (s/s)<br>` +
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
  <h3>CPU Usage</h3>
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

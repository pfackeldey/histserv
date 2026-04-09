# histserv dashboard UI

A Vite + Svelte 5 + TypeScript single-page app with D3.js charts.  It connects to the histserv FastAPI bridge over WebSocket and REST to display real-time server health and histogram visualizations.

---

## Prerequisites

[pixi](https://pixi.sh) manages Node.js, bun, and pre-commit.

```shell
curl -fsSL https://pixi.sh/install.sh | bash
```

---

## pixi task reference

All tasks are in the `dashboard` feature environment.  Run them with `pixi run -e dashboard <task>` from the repo root, or just `pixi run <task>` if the dashboard environment is active.

| Task | Command | Description |
|------|---------|-------------|
| `dashboard-install` | `bun install` | Install `node_modules` (run once, or after `bun.lock` changes) |
| `dashboard-dev` | `bun run dev` | Start Vite HMR dev server on :5173 |
| `dashboard-build` | `bun run build` | Production bundle → `dist/` |
| `dashboard-test` | `bun run test` | Vitest unit tests |
| `dashboard-lint` | `bun run lint` | ESLint |
| `dashboard-format` | `bun run format` | Prettier (writes files) |
| `dashboard-format-check` | `bun run format:check` | Prettier formatting check |
| `dashboard-check` | `bun run check` | svelte-check + tsc |
| `dashboard-serve` | start server + dev | Run histserv + Vite dev server together |

---

## Development workflow

### Start everything together

```shell
pixi run -e dashboard dashboard-install
pixi run -e dashboard dashboard-serve
```

This uses `concurrently` to run `histserv --port 50051 --dashboard-port 8050` and the Vite dev server simultaneously.  Open [http://localhost:5173](http://localhost:5173).  The dev server proxies `/api` and `/ws` to `:8050`.

### Running independently

```shell
# Terminal 1 — Python server
histserv --port 50051 --dashboard-port 8050

# Terminal 2 — Vite dev server
pixi run -e dashboard dashboard-dev
```

---

## Testing

```shell
pixi run -e dashboard dashboard-install
pixi run -e dashboard dashboard-test
```

31 unit tests across 4 files: `ServerOverview`, `HistogramView`, `uhi-axis`, `websocket`.  Uses [Vitest](https://vitest.dev) + [@testing-library/svelte](https://testing-library.com/docs/svelte-testing-library/intro/).

---

## Linting and formatting

```shell
pixi run -e dashboard dashboard-lint      # ESLint
pixi run -e dashboard dashboard-format    # Prettier (writes)
pixi run -e dashboard dashboard-check     # svelte-check + tsc
```

Or run all pre-commit hooks at once (from the repo root):

```shell
pixi run -e dev lint
```

---

## Production build

```shell
pixi run -e dashboard dashboard-build     # outputs to dist/
```

The `dist/` directory is served by histserv when `--dashboard-port` is set.  It is auto-built during `hatch build` via `hatch_build.py`.

---

## Architecture

```
src/
  App.svelte              # root — renders <Layout />
  main.ts                 # Svelte 5 mount
  lib/
    components/
      Layout.svelte        # header / sidebar / content grid
      ServerOverview.svelte
      CpuUsage.svelte
      RpcThroughput.svelte
      HistogramLookup.svelte   # hist_id + token form → metadata display
      HistogramView.svelte     # subscribes to a slice, renders D3 chart
    stores/
      websocket.ts         # WS connection, auto-reconnect, message bus
      stats.ts             # rolling 60-point health history
      histogramMeta.ts     # hist_meta store (UHI axis schema)
      histogramData.ts     # hist_data store + subscribe/unsubscribe helpers
    types/
      protocol.ts          # TypeScript types for WS protocol + UHI axes
    d3-histogram.ts        # D3 rendering: 1D bar chart, 2D heatmap
    uhi-axis.ts            # UHI axis → RenderAxis + flow-bin trimming
  __tests__/
    ServerOverview.test.ts
    HistogramView.test.ts
    uhi-axis.test.ts
    websocket.test.ts
```

**WebSocket URL** is computed at runtime from `window.location.host` so it works on any port in production.  In dev, Vite proxies `/ws` to `ws://localhost:8050`.

See [histserv README § Dashboard](../../../README.md) for the full server-side API and WebSocket protocol reference.

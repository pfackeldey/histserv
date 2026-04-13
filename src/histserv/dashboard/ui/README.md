# histserv dashboard UI

histserv includes an optional real-time observability dashboard.  It is a
read-only web UI that shows server health, lists live histograms, and renders
them as they are filled.

A Vite + Svelte 5 + TypeScript single-page app with D3.js charts.  It connects to the histserv FastAPI bridge over WebSocket and REST to display real-time server health and histogram visualizations.


### Install the dashboard extra

```shell
pip install "histserv[dashboard]"
```

This pulls in FastAPI, uvicorn, and httpx alongside the base install.

### Start the server with the dashboard

Pass `--dashboard-port` to expose the observability interface:

```shell
histserv --port 50051 --dashboard-port 8050
```

Open [http://localhost:8050](http://localhost:8050) in a browser (once a
frontend bundle has been built; see below) or connect directly to the
WebSocket at `ws://localhost:8050/ws`.

---

## Development

### Prerequisites

[pixi](https://pixi.sh) manages Node.js, bun, and pre-commit.

```shell
curl -fsSL https://pixi.sh/install.sh | bash
```

---

### pixi task reference

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

### Testing

```shell
pixi run -e dashboard dashboard-install
pixi run -e dashboard dashboard-test
```

31 unit tests across 4 files: `ServerOverview`, `HistogramView`, `uhi-axis`, `websocket`.  Uses [Vitest](https://vitest.dev) + [@testing-library/svelte](https://testing-library.com/docs/svelte-testing-library/intro/).

---

### Linting and formatting

```shell
pixi run -e dashboard dashboard-lint      # ESLint
pixi run -e dashboard dashboard-format    # Prettier (writes)
pixi run -e dashboard dashboard-check     # svelte-check + tsc
```

Or run all pre-commit hooks at once (from the repo root):

```shell
pixi run -e dev lint
```

### Production build

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

## Network Architecture

**WebSocket URL** is computed at runtime from `window.location.host` so it works on any port in production.  In dev, Vite proxies `/ws` to `ws://localhost:8050`.

The dashboard port exposes:

| Path | Description |
|------|-------------|
| `GET /api/histograms/{hist_id}/metadata` | Histogram metadata including chunk-axis categories |
| `GET /api/histograms/{hist_id}` | One-shot JSON snapshot of a selected dense chunk |
| `WS  /ws` | Subscription-based streaming protocol (primary) |
| `/*` | Serves the built Svelte frontend (production only) |

### WebSocket protocol

All messages share an envelope:

```json
{ "type": "string", "ts": 1712500000.123, "payload": { ... } }
```

**Client → server**

| type | payload | description |
|------|---------|-------------|
| `subscribe` | `{ "streams": ["stats", "hist_list"] }` | Periodic server stats and histogram list |
| `subscribe_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" }, "rate_limit_hz": 1 }` | Stream one dense chunk |
| `unsubscribe_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" } }` | Stop streaming one dense chunk |
| `get_hist` | `{ "hist_id": "…", "selection": { "dataset": "data" } }` | One-shot dense chunk fetch |

**Server → client**

| type | description |
|------|-------------|
| `stats` | Server health (uptime, rpc counts, cpu, memory) — ~1 s |
| `hist_list` | Live histogram summaries, including current chunk-axis categories — ~2 s |
| `hist_meta` | One-shot dense histogram schema for a selected histogram |
| `hist_data` | Dense chunk payload (`selection`, `values`, `version`) |
| `error` | `{ "message": "…", "code": "NOT_FOUND" \| "INTERNAL" }` |

Dashboard histogram fetches always require a full chunk selection expressed as a
JSON object keyed by chunk-axis name. For histograms without chunk axes, the
selection is the empty object encoded as `{}`:

```text
/api/histograms/<hist_id>?selection=%7B%7D
```

---
parent: high-level-design
prefix: TEL
---

# Telemetry

## Context and Design Philosophy

A maintainer running the service wants to know, while agents are playing, how long each tool takes to answer and how its calls are being answered, and whether the HTTP endpoint itself is failing. This component measures that and sends it to a monitoring stack that shows it on a dashboard (HLD goal 12).

Telemetry describes the service, not the games. It measures each tool call and each HTTP request as the MCP adapter answered it, from the outside: it never reaches into the application or the domain, never reads a game, and never changes what an agent is told or what is recorded. A service whose metrics cannot be sent — no endpoint configured, the endpoint down, or recording itself failing — answers every call exactly as it would otherwise.

Measurements are OpenTelemetry metrics, pushed over OTLP to an endpoint named by the standard OpenTelemetry settings. Nothing is sent unless an endpoint is set, so tests and an unconfigured service export nothing. The repository carries a monitoring stack that receives OTLP and shows a provisioned dashboard, so starting it beside a running service is all a maintainer needs.

## What Is Measured

Two histograms, both in seconds. A histogram's count is the number of calls or requests, so call counts by status and request counts by status code come from the same instruments; no separate counters are kept.

| Instrument | Unit | Attributes | Measures |
|---|---|---|---|
| `goldfishing.tool_call.duration` | `s` | `tool.name`, `tool.status` | One MCP tool call |
| `http.server.request.duration` | `s` | `http.request.method`, `url.scheme`, `http.route`, `http.response.status_code`, `error.type` | One HTTP request |

The HTTP instrument and its attributes follow OpenTelemetry's semantic conventions for HTTP servers, so a dashboard built for those conventions reads them; where this design departs from the conventions, the Decisions table says so. The tool-call instrument has no convention to follow and takes the service's own namespace.

### Tool calls

A tool call is timed from the moment the MCP server's call handler receives it to the moment that handler has its result, or raises. Every call that reaches the handler is timed, including one naming a tool that does not exist. The duration includes the time the call waits for a worker thread and for its game's lock, since that is time the agent waits.

`tool.name` is the name of the tool called: one of the thirteen tools, or `unknown`. `tool.status` is how the call ended:

| `tool.status` | When |
|---|---|
| `OK`, `REJECTED`, `CHOICE`, `ERROR` | The tool answered with that status word, including an `ERROR` for arguments of the wrong shape |
| `PROTOCOL_ERROR` | The call named a tool that does not exist and was answered as a protocol error; its `tool.name` is `unknown` |
| `DEFECT` | The tool raised an exception instead of answering; the exception goes on exactly as it would unmeasured |
| `CANCELLED` | The call was cancelled before it had a result, as when the client goes away during a long `wait`; the cancellation goes on exactly as it would unmeasured |

The status word is the one the tools component defines; the tool surface returns it beside the response text, so telemetry never reads it out of the text. A name the client chose is never an attribute value: an unknown tool is counted under `unknown`, so a client cannot create new time series by calling made-up tools.

A `wait` call's duration is mostly time spent waiting by design — up to its timeout of 30 seconds by default and 60 at most. It is measured like any other tool, and the dashboard shows it apart from the rest.

### HTTP requests

An HTTP request is timed from the moment the application receives it until its response has ended — the last body chunk sent — however long a streamed response stays open.

| Attribute | Value |
|---|---|
| `http.request.method` | The request's method if it is one of `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE`, `PATCH`; otherwise `_OTHER` |
| `url.scheme` | The request's scheme, `http` or `https` |
| `http.route` | `/mcp` or `/health` when the request's path is exactly that route; otherwise `other` |
| `http.response.status_code` | The status code of the response the application started; `500` when the application raised before starting one, since that is what the server then sends; absent when the request was cancelled before a response started |
| `error.type` | The exception's fully qualified class name when the application raised, before or after starting a response; otherwise `cancelled` when the request was cancelled before a response started; otherwise the status code as text (`"503"`) when the response's status code is 500 or above; otherwise absent |

An exception or cancellation, before or after the response started, goes on exactly as it would unmeasured; the request is recorded first.

Nearly every MCP request is answered `200` whatever its tool's status. The HTTP instrument shows transport-level failures — refused hosts, malformed MCP requests, server faults — and the tool-call instrument shows how tools answered. Because a `wait` call is one HTTP request to `/mcp`, `/mcp` latency includes the time seats spend waiting.

### Bucket boundaries

Percentiles are estimated from histogram buckets, so both instruments use explicit boundaries chosen for this service, in seconds: 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 15, 20, 25, 30, 35, 45, 60, 65, 90. Ordinary calls fall in the finely spaced range below one second. A `wait` that runs to its timeout lands just above 30 or 60 seconds, in the buckets ending at 35 and 65, rather than in a bucket spanning both.

### Recording never reaches a call

Recording a measurement never changes how a call or request is answered. If recording raises, the failure is logged and swallowed, and the call's result, exception or cancellation goes on as it would have.

## Configuration

Telemetry is configured with OpenTelemetry's standard environment variables, read when the service starts.

| Setting | Environment variable | Default |
|---|---|---|
| Where metrics are pushed | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, used as given (it names the full URL, ending in `/v1/metrics`); else `OTEL_EXPORTER_OTLP_ENDPOINT`, with `/v1/metrics` appended | Unset: nothing is exported |
| Time between pushes, in milliseconds | `OTEL_METRIC_EXPORT_INTERVAL` | `5000` |
| Service name on every measurement | `OTEL_SERVICE_NAME`, else a `service.name` in `OTEL_RESOURCE_ATTRIBUTES` | `mtg-goldfishing` |
| Other resource attributes | `OTEL_RESOURCE_ATTRIBUTES` | none |
| Headers sent with each push, and the push timeout | `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_TIMEOUT` and their `_METRICS_` forms | none; OpenTelemetry's default timeout |
| Turning telemetry off | `OTEL_SDK_DISABLED=true`, or `OTEL_METRICS_EXPORTER=none` | on when an endpoint is set |

Pushes use OTLP over HTTP with protobuf, the only protocol the service sends. Every measurement carries a `service.instance.id`, a new random id each time the service starts unless `OTEL_RESOURCE_ATTRIBUTES` gives one, so that several processes pushing to one store keep separate series.

The service refuses to start, with a message naming the variable and exit status 2, as it does for an unusable port, when:

- an endpoint variable is set but is not an `http://` or `https://` URL;
- `OTEL_METRIC_EXPORT_INTERVAL` is set but is not a whole number of milliseconds greater than zero;
- `OTEL_EXPORTER_OTLP_PROTOCOL` or `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` is set to anything but `http/protobuf`;
- `OTEL_METRICS_EXPORTER` is set to anything but `otlp` or `none`.

An empty variable counts as unset, as it does for the service's own settings.

With no endpoint set, or telemetry turned off, measurements are still taken but go nowhere. Exporting runs on a background thread; a push that fails is dropped and does not reach any call. The export interval defaults to five seconds, shorter than OpenTelemetry's sixty, so the dashboard is live.

When the service stops, after the HTTP server has finished the requests in flight, the meter provider is shut down — pushing what was measured since the last push, waiting at most five seconds — and then the database and card catalog are closed.

## Where It Sits

Telemetry is an adapter, in `src/mtg_goldfishing/adapters/telemetry/`. Under `src/`, it and the composition root are the only modules that import OpenTelemetry; tests may import OpenTelemetry's in-memory reader to read measurements back.

No adapter imports another (APP-003), so telemetry and the MCP adapter are connected only by the composition root:

- **Service metrics.** The telemetry adapter's one object, built over an OpenTelemetry meter provider, offers two operations: record a tool call (tool name, status, seconds) and record an HTTP request (method, scheme, path, status code or none, error type or none, seconds). It owns the instrument names, attribute names, bucket boundaries, and the folding of unknown methods and paths into `_OTHER` and `other`.
- **The tool-call listener.** The MCP adapter declares a tool-call listener: a callable taking a tool name, a status and a duration in seconds. `mcp_server` and `create_app` accept one as an optional argument, and with none given nothing is measured. When a listener is given, the MCP server times each call in its call handler and calls the listener with the call's outcome — naming a tool that does not exist as `unknown`, since only the MCP adapter knows which tools exist — swallowing and logging anything the listener raises.
- **The HTTP middleware.** The telemetry adapter provides an ASGI middleware that is given the service metrics and the application's measured routes. It wraps the whole application, so every request — to `/mcp`, `/health`, any other path, and requests the MCP transport refuses — is measured.
- **Composition.** The composition root reads the telemetry settings and builds the meter provider — with an OTLP exporter on a periodic reader when export is on, with no reader otherwise — builds the service metrics over it, passes their tool-call recording to `create_app` as the listener, adds the middleware to the application with the routes `/mcp` and `/health`, and shuts the meter provider down when the service stops.

Durations are measured with a monotonic timer that the timing code receives when built, defaulting to the system's performance counter, so tests can supply a timer whose readings they choose.

Telemetry is not a port: the application never calls it, and nothing in it is a domain type. It therefore has no contract suite. Tests build the service metrics over a meter provider with OpenTelemetry's in-memory metric reader and read measurements back from it; nothing is mocked and nothing is sent. The end-to-end harness starts the real process with every `OTEL_` variable removed from its environment, so a developer's shell settings never make a test export.

## Monitoring Stack

The repository's `monitoring/` directory holds a Compose file that runs Grafana's `otel-lgtm` image — an OpenTelemetry collector, a Prometheus metrics store and Grafana in one container — at a pinned version. It publishes OTLP over HTTP on port `4318`, OTLP over gRPC on `4317`, and Grafana on `3000`, each bound to `127.0.0.1` only. The store's data is kept in a named volume, so history survives restarting the container. Grafana opens without a login, as the image provides for local use.

The README tells a maintainer how to watch the service: start the stack with `docker compose -f monitoring/compose.yaml up -d`, start the service with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, and open Grafana at `http://localhost:3000`.

The collector stores the instruments as Prometheus metrics, under the names the pinned image's translation gives them; the dashboard's queries use those names, and they are checked against a running stack whenever the pinned version changes.

## Dashboard

The dashboard, *MTG Goldfishing*, is provisioned from a JSON file in `monitoring/`, so it is present whenever the stack starts and changes to it are reviewed like code. It refreshes every five seconds and opens on the last fifteen minutes. A `tool` variable, listing every tool seen, filters the tool panels; it includes every tool by default.

| Panel | Shows |
|---|---|
| Tool latency | p50, p95 and p99 of tool-call duration over time, across the selected tools other than `wait` |
| Latency by tool | p50, p95 and p99 of each tool's duration over the selected time range, one row per tool, `wait` included |
| Tool calls by status | Rate of tool calls over time, stacked by `tool.status` |
| Tool error rate | Share of tool calls answered `ERROR`, `PROTOCOL_ERROR` or `DEFECT` over time |
| Calls by tool and status | Count of calls over the selected time range, one row per tool, one column per status |
| `wait` latency | p50, p95 and p99 of `wait` duration over time |
| HTTP latency | p50, p95 and p99 of HTTP request duration over time, by route |
| HTTP requests by status code | Rate of HTTP requests over time, stacked by status code |

Percentiles are computed by Prometheus from the bucket series, summed across service instances, over a rolling one-minute window for time series and over the selected range for tables. The HTTP latency panel describes the transport, `wait` included; tool latency without `wait` is on the tool panels.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| How tool calls are counted by status | The tool-call histogram's count, by `tool.status` | A separate counter | A histogram's count is exactly the number of calls; a second instrument would be a second source for one number. |
| Where the status word comes from | The tool surface returns it beside the response text | Reading the first word of the response text | In a contested game the digest comes before the status word, so the text's first word is not reliably the status. |
| How the MCP adapter and telemetry connect | A tool-call listener callable declared by the MCP adapter, and a middleware added by the composition root | The MCP adapter importing the service metrics; a port in the application | Adapters may not import each other (APP-003). A port belongs to the application, which never measures anything and whose ports speak in domain types; HTTP requests are not an application concept. A callable needs no shared import, and the composition root is already the one place that connects adapters. |
| Contract suite for telemetry | None | A contract suite like the ports' | Contract suites state what a port promises across its implementations; telemetry is not a port and has one implementation, tested against OpenTelemetry's in-memory reader. |
| HTTP measurement | A middleware written for this service, recording the semantic-convention instrument | OpenTelemetry's FastAPI or ASGI instrumentation packages | The packages add several dependencies, record the older millisecond instrument unless opted out, and would label routes through their own matching; a short middleware records exactly the convention's instrument with bounded attribute values. |
| Unmatched paths | `http.route` set to `other` | Leaving `http.route` unset, as the conventions say | A named series shows on the dashboard beside `/mcp` and `/health` without query-side relabelling, and the departure affects only requests for paths the service does not serve. |
| Tool-call instrument name | `goldfishing.tool_call.duration` in the service's namespace | A draft MCP semantic convention | No stable convention covers MCP tool calls; a namespaced name cannot collide with one later. |
| Client-chosen values | Unknown tools, methods and paths folded into `unknown`, `_OTHER` and `other` | Recorded as given | Attribute values a client chooses would let any client create unbounded time series. |
| Percentile accuracy | Explicit buckets tuned to the service's range, with edges just above `wait`'s timeouts | Exponential histograms | Exponential histograms need native-histogram support in the metrics store; explicit buckets work with every Prometheus and give enough resolution where calls fall. |
| Unusable telemetry settings | Refuse to start, exit status 2 | Warn and fall back to defaults, as OpenTelemetry does | The service already refuses an unusable port; a maintainer who set an endpoint and sees no metrics because of a typo has a harder problem than one told at start-up. |
| Export interval | 5 seconds by default, overridable | OpenTelemetry's default of 60 seconds | A dashboard a minute behind is not live; the push is a small request on a background thread. |
| OTLP transport | HTTP with protobuf only | gRPC; both | Fewer and lighter dependencies; the stack accepts both, and one protocol is one code path. |
| Instance identity | A random `service.instance.id` per start | None | Without it, several processes pushing to one store overwrite each other's cumulative series, which a hosted deployment would hit. |
| Timing a `wait` | Measured like every tool and shown in its own panel | Excluded from measurement | `wait` latency is real data — how long seats wait on each other — but it would swamp the other tools' percentiles if pooled with them. |
| Data kept by the stack | A named volume | Container-local storage only | A maintainer restarting the stack keeps the history they were looking at. |

## Open Questions & Future Decisions

### Deferred
1. Traces of individual calls — the use case, the lock wait, the database and card fetches as spans — when an aggregate latency points at a slow call that needs explaining.
2. Alerting rules on the stack, when the service is run unattended.
3. Metrics for the Scryfall card fetches on their own, if `load_deck` latency needs explaining.

## References

- `docs/high-level-design.md` (goal 12; Key Design Decisions, *Telemetry is OpenTelemetry metrics pushed over OTLP to a local all-in-one stack*)
- `docs/intent/tools/tools-design.md` (the status words; serving)
- `docs/intent/application/application-specs.md` (APP-003, the import rule)
- OpenTelemetry semantic conventions for HTTP metrics: `https://opentelemetry.io/docs/specs/semconv/http/http-metrics/`
- OpenTelemetry SDK environment variables: `https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/`
- Grafana `otel-lgtm`: `https://github.com/grafana/docker-otel-lgtm`

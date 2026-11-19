# Telemetry — Specs

Design: `telemetry-design.md`. Prefix: `TEL`.

## Tool calls

- [ ] **TEL-001**: When the MCP server's call handler receives a tool call and a tool-call listener was given, the MCP server shall call the listener exactly once for that call, with the tool name, the status, and the seconds from the handler receiving the call to the handler having its result or raising.
- [ ] **TEL-002**: When a tool answers a call, the MCP server shall pass to the tool-call listener the status word of that answer: `OK`, `REJECTED`, `CHOICE` or `ERROR`, an `ERROR` for arguments of the wrong shape included.
- [ ] **TEL-003**: When a tool call names a tool that does not exist, the MCP server shall pass `unknown` as the tool name and `PROTOCOL_ERROR` as the status to the tool-call listener, and shall answer the call with the same protocol error it gives when no listener was given.
- [ ] **TEL-004**: When a tool raises an exception instead of answering, the MCP server shall pass `DEFECT` as the status to the tool-call listener and then let that same exception propagate.
- [ ] **TEL-005**: When a tool call is cancelled before the MCP server's call handler has its result, the MCP server shall pass `CANCELLED` as the status to the tool-call listener and then let the cancellation propagate.
- [ ] **TEL-006**: If the tool-call listener raises, then the MCP server shall log the failure and answer the call with the result, exception or cancellation it would have had with no listener.
- [ ] **TEL-007**: Where no tool-call listener is given to `mcp_server` or `create_app`, the MCP adapter shall serve every call as it does with one, and shall measure nothing.
- [ ] **TEL-008**: The tool surface shall return, with each call's response text, the status word of that response.
- [ ] **TEL-009**: When the service metrics record a tool call, they shall record one measurement of the histogram `goldfishing.tool_call.duration`, in unit `s`, with the attribute `tool.name` set to the tool name and `tool.status` set to the status as given.

## HTTP requests

- [ ] **TEL-010**: While the HTTP middleware wraps the application, the middleware shall record one measurement of the histogram `http.server.request.duration`, in unit `s`, for each HTTP request the application receives, timed from receiving the request until its response has ended or the application raised or was cancelled.
- [ ] **TEL-011**: When the HTTP middleware records a request, it shall set `http.request.method` to the request's method if that is one of `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE` or `PATCH`, and to `_OTHER` otherwise.
- [ ] **TEL-012**: When the HTTP middleware records a request, it shall set `url.scheme` to the request's scheme.
- [ ] **TEL-013**: When the HTTP middleware records a request, it shall set `http.route` to the request's path if the path is exactly one of the measured routes the middleware was given, and to `other` otherwise.
- [ ] **TEL-014**: When the application started a response to a request, the HTTP middleware shall set `http.response.status_code` to that response's status code.
- [ ] **TEL-015**: When the application raised before starting a response, the HTTP middleware shall set `http.response.status_code` to `500`.
- [ ] **TEL-016**: When the application was cancelled before starting a response, the HTTP middleware shall record the request without `http.response.status_code`.
- [ ] **TEL-017**: When the application raised while handling a request, before or after starting a response, the HTTP middleware shall set `error.type` to the exception's fully qualified class name and then let that same exception propagate.
- [ ] **TEL-018**: When the application was cancelled while handling a request, the HTTP middleware shall let the cancellation propagate, having set `error.type` to `cancelled` if no response had started.
- [ ] **TEL-019**: When the application neither raised nor was cancelled before starting a response and the response's status code is 500 or above, the HTTP middleware shall set `error.type` to the status code as text; when the application neither raised nor was cancelled and the status code is below 500, it shall set no `error.type`.
- [ ] **TEL-020**: If recording a request raises, then the HTTP middleware shall log the failure and let the request's response, exception or cancellation go on as it would have unmeasured.

## Both instruments

- [ ] **TEL-021**: The service metrics shall give `goldfishing.tool_call.duration` and `http.server.request.duration` the explicit bucket boundaries, in seconds, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 15, 20, 25, 30, 35, 45, 60, 65, 90.
- [ ] **TEL-022**: No module under `src/mtg_goldfishing` other than modules under `mtg_goldfishing.adapters.telemetry` and the composition root `mtg_goldfishing.bootstrap` shall import `opentelemetry`.
- [ ] **TEL-023**: An automated architecture test shall fail when the import rule TEL-022 is broken.

## Composition

- [ ] **TEL-024**: When the service starts, the composition root shall build the service metrics, pass their tool-call recording to `create_app` as the tool-call listener, and wrap the application in the HTTP middleware with the measured routes `/mcp` and `/health`.
- [ ] **TEL-025**: When the service stops, the composition root shall, after the HTTP server has finished the requests in flight, shut down the meter provider — pushing what was measured since the last push and waiting at most five seconds — and only then close the database and the card catalog.

## Configuration

- [ ] **TEL-026**: If neither `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` nor `OTEL_EXPORTER_OTLP_ENDPOINT` is set to a non-empty value, then the service shall export no metrics.
- [ ] **TEL-027**: When `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set to a non-empty value and telemetry is not turned off (TEL-032), the service shall push metrics to that URL exactly as given, over OTLP using HTTP with protobuf.
- [ ] **TEL-028**: When `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is unset or empty, `OTEL_EXPORTER_OTLP_ENDPOINT` is set to a non-empty value, and telemetry is not turned off (TEL-032), the service shall push metrics over OTLP using HTTP with protobuf to that URL with the path `v1/metrics` appended after a single `/`.
- [ ] **TEL-029**: While the service exports metrics, it shall push them every `OTEL_METRIC_EXPORT_INTERVAL` milliseconds, defaulting to 5000 when that variable is unset or empty.
- [ ] **TEL-030**: The service shall give every measurement the resource attribute `service.name` set to `OTEL_SERVICE_NAME` when that is non-empty, else to the `service.name` in `OTEL_RESOURCE_ATTRIBUTES` when that gives one, else to `mtg-goldfishing`.
- [ ] **TEL-031**: The service shall give every measurement the resource attribute `service.instance.id` set to the `service.instance.id` in `OTEL_RESOURCE_ATTRIBUTES` when that gives one, else to a random id chosen anew each time the service starts.
- [ ] **TEL-032**: When `OTEL_SDK_DISABLED` is `true`, ignoring case, or `OTEL_METRICS_EXPORTER` is `none`, the service shall export no metrics, whatever endpoint is set.
- [ ] **TEL-033**: The service shall give every measurement each resource attribute named in `OTEL_RESOURCE_ATTRIBUTES`.
- [ ] **TEL-034**: While the service exports metrics, it shall send with each push the headers in `OTEL_EXPORTER_OTLP_METRICS_HEADERS`, else in `OTEL_EXPORTER_OTLP_HEADERS`, and shall use the timeout in `OTEL_EXPORTER_OTLP_METRICS_TIMEOUT`, else in `OTEL_EXPORTER_OTLP_TIMEOUT`, else OpenTelemetry's default.
- [ ] **TEL-035**: If `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT` is set to a non-empty value that is not a URL with scheme `http` or `https` and a host, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [ ] **TEL-036**: If `OTEL_METRIC_EXPORT_INTERVAL` is set to a non-empty value that is not a whole number greater than zero, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [ ] **TEL-037**: If `OTEL_EXPORTER_OTLP_PROTOCOL` or `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` is set to a non-empty value other than `http/protobuf`, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [ ] **TEL-038**: If `OTEL_METRICS_EXPORTER` is set to a non-empty value other than `otlp` or `none`, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [ ] **TEL-039**: If a push of metrics fails, then the service shall drop that push and answer every call as it would have had the push succeeded.
- [ ] **TEL-040**: The response to a call, its call record and the game's state shall be the same whether or not telemetry is configured and whether or not its endpoint is reachable.
- [ ] **TEL-041**: The end-to-end harness shall start the service with every environment variable whose name begins with `OTEL_` removed.

## Monitoring stack

- [ ] **TEL-042**: The repository shall carry `monitoring/compose.yaml`, running the `grafana/otel-lgtm` image at a pinned version tag other than `latest`.
- [ ] **TEL-043**: `monitoring/compose.yaml` shall publish the container's ports 4318 (OTLP over HTTP), 4317 (OTLP over gRPC) and 3000 (Grafana), each on the host address `127.0.0.1` only.
- [ ] **TEL-044**: `monitoring/compose.yaml` shall keep the container's stored data in a named volume.
- [ ] **TEL-045**: `monitoring/compose.yaml` shall provision Grafana with the dashboard JSON file kept in `monitoring/`, so that the dashboard is present when the stack starts.
- [ ] **TEL-046**: When the stack is running and the service pushes to `http://localhost:4318`, every panel of the dashboard shall show the service's measurements, its queries naming the metrics as the pinned image stores them.
- [ ] **TEL-047**: The README shall say how to start the stack, how to start the service pushing to it, and where to open the dashboard.

## Dashboard

- [ ] **TEL-048**: The dashboard shall be titled `MTG Goldfishing`, refresh every five seconds, and open on the last fifteen minutes.
- [ ] **TEL-049**: The dashboard shall have a `tool` variable listing every `tool.name` seen, allowing several to be selected and including all by default, and every tool panel shall show only the selected tools.
- [ ] **TEL-050**: The dashboard shall have a *Tool latency* time-series panel showing the p50, p95 and p99 of tool-call duration across the selected tools other than `wait`.
- [ ] **TEL-051**: The dashboard shall have a *Latency by tool* table showing, for each selected tool, `wait` included, the p50, p95 and p99 of its duration over the selected time range.
- [ ] **TEL-052**: The dashboard shall have a *Tool calls by status* time-series panel showing the rate of tool calls stacked by `tool.status`.
- [ ] **TEL-053**: The dashboard shall have a *Tool error rate* time-series panel showing the share of tool calls whose `tool.status` is `ERROR`, `PROTOCOL_ERROR` or `DEFECT`.
- [ ] **TEL-054**: The dashboard shall have a *Calls by tool and status* table showing the count of calls over the selected time range, one row per tool and one column per `tool.status`.
- [ ] **TEL-055**: The dashboard shall have a *`wait` latency* time-series panel showing the p50, p95 and p99 of `wait` duration.
- [ ] **TEL-056**: The dashboard shall have an *HTTP latency* time-series panel showing the p50, p95 and p99 of HTTP request duration for each `http.route`.
- [ ] **TEL-057**: The dashboard shall have an *HTTP requests by status code* time-series panel showing the rate of HTTP requests stacked by `http.response.status_code`.
- [ ] **TEL-058**: The dashboard shall compute each percentile from the histogram's bucket series summed across service instances, over a rolling one-minute window in time-series panels and over the selected time range in tables.

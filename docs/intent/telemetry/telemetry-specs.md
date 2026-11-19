# Telemetry — Specs

Design: `telemetry-design.md`. Prefix: `TEL`.

In these specs, a call or request **raised** when the code handling it raised an exception that is an instance of Python's `Exception`; it was **cancelled** when it raised the cancellation exception of the running async backend (`anyio.get_cancelled_exc_class()`). Any other `BaseException`, such as `KeyboardInterrupt` or `SystemExit`, passes through unrecorded.

## Tool calls

- [x] **TEL-001**: When the MCP server's call handler (the function `mcp_server` registers with the MCP SDK to answer tool calls) receives a tool call and a tool-call listener was given, the MCP server shall call the listener exactly once for that call, with the tool name, the status, and the seconds from the handler receiving the call to the handler returning, raising or being cancelled.
- [x] **TEL-059**: The tool-call listener shall be a synchronous callable, and the MCP server shall call it without awaiting.
- [x] **TEL-002**: When a tool answers a call, the MCP server shall pass to the tool-call listener the status word of that answer: `OK`, `REJECTED`, `CHOICE` or `ERROR`, an `ERROR` for arguments of the wrong shape included.
- [x] **TEL-003**: When a tool call names a tool that does not exist, the MCP server shall pass `unknown` as the tool name and `PROTOCOL_ERROR` as the status to the tool-call listener, and shall answer the call with the same protocol error it gives when no listener was given.
- [x] **TEL-004**: When the tool raised instead of answering, the MCP server shall pass `DEFECT` as the status to the tool-call listener and then re-raise that same exception to the MCP SDK.
- [x] **TEL-005**: When the MCP server's call handler was cancelled before it had the tool's result, the MCP server shall pass `CANCELLED` as the status to the tool-call listener and then re-raise the cancellation; a cancellation that arrives after the handler has the result is not the handler's to record.
- [x] **TEL-006**: If the tool-call listener raises, then the MCP server shall log the failure and answer the call with the result, exception or cancellation it would have had with no listener.
- [x] **TEL-007**: Where no tool-call listener is given to `mcp_server` or `create_app`, the MCP adapter shall serve every call as it does with one, and shall measure nothing.
- [x] **TEL-008**: The tool surface shall return, with each call's response text, the status word of that response, as a value the MCP server reads and never sends to the client.
- [x] **TEL-009**: When the service metrics record a tool call, they shall record one measurement of the histogram `goldfishing.tool_call.duration`, in unit `s`, with the attribute `tool.name` set to the tool name and `tool.status` set to the status as given.

## HTTP requests

- [x] **TEL-010**: While the HTTP middleware wraps the application, the middleware shall record one measurement of the histogram `http.server.request.duration`, in unit `s`, for each ASGI request of type `http` the application receives, timed from receiving the request until the application has returned, raised or been cancelled; requests of any other type, such as `lifespan`, shall pass through unmeasured.
- [x] **TEL-011**: When the HTTP middleware records a request, it shall set `http.request.method` to the request's method if that is one of `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE` or `PATCH`, and to `_OTHER` otherwise.
- [x] **TEL-012**: When the HTTP middleware records a request, it shall set `url.scheme` to the request's scheme.
- [x] **TEL-013**: When the HTTP middleware records a request, it shall set `http.route` to the request's path as the ASGI scope gives it if that path is exactly one of the measured routes the middleware was given, and to `other` otherwise, so that `/mcp/` is `other`.
- [x] **TEL-014**: When the application started a response to a request, the HTTP middleware shall set `http.response.status_code` to that response's status code.
- [x] **TEL-015**: When the application raised before starting a response, or returned without starting one, the HTTP middleware shall set `http.response.status_code` to `500`.
- [x] **TEL-016**: When the application was cancelled before starting a response, the HTTP middleware shall record the request without `http.response.status_code`.
- [x] **TEL-017**: When the application raised while handling a request, before or after starting a response, the HTTP middleware shall set `error.type` to the exception's fully qualified class name, whatever the status code, and then re-raise that same exception.
- [x] **TEL-018**: When the application was cancelled while handling a request, the HTTP middleware shall re-raise the cancellation, having set `error.type` to `cancelled` if no response had started.
- [x] **TEL-019**: When the application did not raise while handling a request and was not cancelled before starting a response, the HTTP middleware shall set `error.type` to the recorded status code as text if that code is 500 or above, and shall set no `error.type` otherwise.
- [x] **TEL-020**: If recording a request raises, then the HTTP middleware shall log the failure and let the request's response, exception or cancellation go on as it would have unmeasured.

## Both instruments

- [x] **TEL-021**: The service metrics shall give `goldfishing.tool_call.duration` and `http.server.request.duration` the explicit bucket boundaries, in seconds, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 15, 20, 25, 30, 35, 45, 60, 65, 90.
- [x] **TEL-022**: No module under `src/mtg_goldfishing` other than modules under `mtg_goldfishing.adapters.telemetry` and the composition root `mtg_goldfishing.bootstrap` shall import `opentelemetry` or a module under it.
- [x] **TEL-023**: An automated architecture test, separate from the tests of APP-004, shall read the import statements of every module under `src/mtg_goldfishing` and fail when one breaks the import rule TEL-022.

## Composition

- [x] **TEL-024**: When the service starts, the composition root shall build the service metrics over a meter provider that has a periodic OTLP reader only when export is on, pass their tool-call recording to `create_app` as the tool-call listener, and wrap the application in the HTTP middleware with the measured routes `/mcp` and `/health`.
- [x] **TEL-025**: When the service stops, the composition root shall, once the HTTP server has stopped and the application's own shutdown has finished, shut down the meter provider — pushing what was measured since the last push and waiting at most five seconds — and then close the database and the card catalog, closing them even if shutting down the meter provider failed.

## Configuration

In this section, the **endpoint in effect** is `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` if that is non-empty, else `OTEL_EXPORTER_OTLP_ENDPOINT` if that is non-empty, else none; the **protocol in effect** is `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` if that is non-empty, else `OTEL_EXPORTER_OTLP_PROTOCOL` if that is non-empty, else `http/protobuf`; telemetry is **turned off** when `OTEL_SDK_DISABLED` is `true` or `OTEL_METRICS_EXPORTER` is `none`, both ignoring case; and **export is on** when there is an endpoint in effect and telemetry is not turned off. An empty variable counts as unset.

- [x] **TEL-026**: If there is no endpoint in effect, then the service shall export no metrics.
- [x] **TEL-032**: When telemetry is turned off, the service shall export no metrics, whatever endpoint is set, and shall not check the endpoint, protocol or export interval variables.
- [x] **TEL-027**: When export is on and the endpoint in effect is `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, the service shall push metrics to that URL exactly as given, over OTLP using HTTP with protobuf.
- [x] **TEL-028**: When export is on and the endpoint in effect is `OTEL_EXPORTER_OTLP_ENDPOINT`, the service shall push metrics over OTLP using HTTP with protobuf to that URL with the path `v1/metrics` appended after a single `/`.
- [x] **TEL-029**: While export is on, the service shall push metrics every `OTEL_METRIC_EXPORT_INTERVAL` milliseconds, defaulting to 5000 when that variable is unset.
- [x] **TEL-030**: The service shall give every measurement the resource attribute `service.name` set to `OTEL_SERVICE_NAME` when that is non-empty, else to the `service.name` in `OTEL_RESOURCE_ATTRIBUTES` when that gives one, else to `mtg-goldfishing`.
- [x] **TEL-031**: The service shall give every measurement the resource attribute `service.instance.id` set to the `service.instance.id` in `OTEL_RESOURCE_ATTRIBUTES` when that gives one, else to a random id chosen anew each time the service starts.
- [x] **TEL-033**: The service shall give every measurement each other resource attribute named in `OTEL_RESOURCE_ATTRIBUTES`, `service.name` and `service.instance.id` following TEL-030 and TEL-031.
- [x] **TEL-034**: While export is on, the service shall leave the push headers and timeout (`OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_TIMEOUT` and their `_METRICS_` forms) to OpenTelemetry's OTLP exporter, which reads and applies them itself, and shall not check them.
- [x] **TEL-035**: If export is on and the endpoint in effect is not a URL with scheme `http` or `https` and a host, then the service shall refuse to start, printing a message that names the variable that gave it and exiting with status 2.
- [x] **TEL-036**: If export is on and `OTEL_METRIC_EXPORT_INTERVAL` is set to a value that is not a whole number greater than zero, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [x] **TEL-037**: If export is on and the protocol in effect is not `http/protobuf`, ignoring case, then the service shall refuse to start, printing a message that names the variable that gave it and exiting with status 2.
- [x] **TEL-038**: If `OTEL_METRICS_EXPORTER` is set to a value other than `otlp` or `none`, ignoring case, then the service shall refuse to start, printing a message that names the variable and exiting with status 2.
- [x] **TEL-039**: If a push of metrics fails, then the service shall drop that push and answer every call as it would have had the push succeeded.
- [x] **TEL-040**: The response to a call, its call record and the game's state shall be the same whether or not telemetry is configured and whether or not its endpoint is reachable.
- [x] **TEL-041**: The end-to-end harness shall start the service with every environment variable whose name begins with `OTEL_` removed.

## Monitoring stack

- [x] **TEL-042**: The repository shall carry `monitoring/compose.yaml`, running the `grafana/otel-lgtm` image at a pinned version tag other than `latest`.
- [x] **TEL-043**: `monitoring/compose.yaml` shall publish the container's ports 4318 (OTLP over HTTP), 4317 (OTLP over gRPC) and 3000 (Grafana), each on the host address `127.0.0.1` only.
- [x] **TEL-044**: `monitoring/compose.yaml` shall keep the container's stored data in a named volume.
- [x] **TEL-045**: `monitoring/compose.yaml` shall provision Grafana with the dashboard JSON file kept in `monitoring/`, so that the dashboard is present when the stack starts.
- [x] **TEL-046**: When the stack is running and the service pushes to `http://localhost:4318`, every panel of the dashboard shall show the service's measurements, its queries naming the metrics as the pinned image stores them.
- [x] **TEL-047**: The README shall say how to start the stack, how to start the service pushing to it, and where to open the dashboard.

## Dashboard

- [x] **TEL-048**: The dashboard shall be titled `MTG Goldfishing`, refresh every five seconds, and open on the last fifteen minutes.
- [x] **TEL-049**: The dashboard shall have a `tool` variable listing every `tool.name` seen, `unknown` included once seen, allowing several to be selected and including all by default; every tool panel except *`wait` latency* shall show only the selected tools.
- [x] **TEL-050**: The dashboard shall have a *Tool latency* time-series panel showing the p50, p95 and p99 of tool-call duration across the selected tools other than `wait`.
- [x] **TEL-051**: The dashboard shall have a *Latency by tool* table showing, for each selected tool, `wait` included, the p50, p95 and p99 of its duration over the selected time range.
- [x] **TEL-052**: The dashboard shall have a *Tool calls by status* time-series panel showing the rate of calls to the selected tools stacked by `tool.status`.
- [x] **TEL-053**: The dashboard shall have a *Tool error rate* time-series panel showing, among calls to the selected tools other than `wait`, the share whose `tool.status` is `ERROR`, `PROTOCOL_ERROR` or `DEFECT`.
- [x] **TEL-054**: The dashboard shall have a *Calls by tool and status* table showing the count of calls to the selected tools over the selected time range, one row per tool and one column per `tool.status`.
- [x] **TEL-055**: The dashboard shall have a *`wait` latency* time-series panel showing the p50, p95 and p99 of `wait` duration, whatever tools are selected.
- [x] **TEL-056**: The dashboard shall have an *HTTP latency* time-series panel showing the p50, p95 and p99 of HTTP request duration for each `http.route`.
- [x] **TEL-057**: The dashboard shall have an *HTTP requests by status code* time-series panel showing the rate of HTTP requests stacked by `http.response.status_code`, requests recorded without a status code shown as `none`.
- [x] **TEL-058**: The dashboard shall compute each percentile from the histogram's bucket series summed across service instances, over a rolling one-minute window in time-series panels and over the selected time range in tables.

"""What the repository carries for watching the service: the monitoring stack's Compose file,
the Grafana provisioning, the dashboard and the README's instructions. Read from the files;
nothing is started.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "monitoring"
COMPOSE = MONITORING / "compose.yaml"
DASHBOARD = MONITORING / "dashboards" / "mtg-goldfishing.json"
PROVIDER = MONITORING / "dashboards.yaml"
README = ROOT / "README.md"

IMAGE = "grafana/otel-lgtm"
STORED_DATA = PurePosixPath("/data")
GRAFANA_PROVISIONING = PurePosixPath("/otel-lgtm/grafana/conf/provisioning/dashboards")

TOOL_METRIC = "goldfishing_tool_call_duration_seconds"
HTTP_METRIC = "http_server_request_duration_seconds"
STORED_METRICS = frozenset(
    f"{metric}_{series}"
    for metric in (TOOL_METRIC, HTTP_METRIC)
    for series in ("bucket", "count", "sum")
)
INSTANCE_LABELS = frozenset({"service_instance_id", "instance", "job"})

TOOL_LATENCY = "Tool latency"
LATENCY_BY_TOOL = "Latency by tool"
CALLS_BY_STATUS = "Tool calls by status"
ERROR_RATE = "Tool error rate"
CALLS_BY_TOOL_AND_STATUS = "Calls by tool and status"
WAIT_LATENCY = "wait latency"
HTTP_LATENCY = "HTTP latency"
HTTP_BY_STATUS_CODE = "HTTP requests by status code"

FILTERED_TOOL_PANELS = (
    TOOL_LATENCY,
    LATENCY_BY_TOOL,
    CALLS_BY_STATUS,
    ERROR_RATE,
    CALLS_BY_TOOL_AND_STATUS,
)
TIME_SERIES_PERCENTILE_PANELS = (TOOL_LATENCY, WAIT_LATENCY, HTTP_LATENCY)
TABLE_PERCENTILE_PANELS = (LATENCY_BY_TOOL,)
PERCENTILES = frozenset({0.5, 0.95, 0.99})
TOOL_SELECTED = re.compile(r'tool_name=~"\$(tool|\{tool\})"')
WAIT_EXCLUDED = 'tool_name!="wait"'
WAIT_ONLY = 'tool_name="wait"'
LABELS = r'(?:[^}"]|"[^"]*")*'
"""The inside of a label selector, quoted values holding braces (`"${tool}"`) included."""


# --- reading the files -------------------------------------------------------------------


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return loaded


def _stack_service() -> dict[str, Any]:
    """The Compose service that runs the all-in-one image."""
    services = [
        service
        for service in _compose()["services"].values()
        if str(service.get("image", "")).startswith(f"{IMAGE}:")
    ]
    assert len(services) == 1, f"expected one service running {IMAGE}, found {len(services)}"
    return services[0]


@dataclass(frozen=True)
class PortBinding:
    host_ip: str | None
    published: str
    target: str


def _port_bindings() -> list[PortBinding]:
    bindings = []
    for port in _stack_service().get("ports", []):
        if isinstance(port, dict):
            bindings.append(
                PortBinding(
                    port.get("host_ip"), str(port.get("published", "")), str(port["target"])
                )
            )
            continue
        parts = str(port).split("/")[0].split(":")
        host_ip = parts[0] if len(parts) == 3 else None
        published = parts[-2] if len(parts) >= 2 else ""
        bindings.append(PortBinding(host_ip, published, parts[-1]))
    return bindings


@dataclass(frozen=True)
class Mount:
    kind: str
    source: str
    target: PurePosixPath


def _mounts() -> list[Mount]:
    named = set((_compose().get("volumes") or {}).keys())
    mounts = []
    for volume in _stack_service().get("volumes", []):
        if isinstance(volume, dict):
            source, target = str(volume.get("source", "")), str(volume["target"])
            kind = str(volume.get("type", "volume"))
        else:
            source, target = str(volume).split(":")[:2]
            kind = "volume" if source in named else "bind"
        mounts.append(Mount(kind, source, PurePosixPath(target)))
    return mounts


def _host_path(mount: Mount) -> Path:
    """Where a bind mount's source is on the host; Compose resolves it from the file's folder."""
    return (MONITORING / mount.source).resolve()


def _dashboard() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    return loaded


def _panels() -> list[dict[str, Any]]:
    """Every panel, those inside collapsed rows included."""
    panels = []
    for panel in _dashboard().get("panels", []):
        panels.append(panel)
        panels.extend(panel.get("panels", []))
    return panels


def _panel(title: str) -> dict[str, Any]:
    found = [panel for panel in _panels() if panel.get("title") == title]
    assert len(found) == 1, f"expected one panel titled {title!r}, found {len(found)}"
    return found[0]


def _targets(panel: dict[str, Any]) -> list[dict[str, Any]]:
    targets = [target for target in panel.get("targets", []) if not target.get("hide")]
    assert targets, f"panel {panel.get('title')!r} has no queries"
    return targets


def _compact(expr: str) -> str:
    """The query with all whitespace removed; no label value the dashboard uses has any."""
    return re.sub(r"\s+", "", expr)


def _exprs(title: str) -> list[str]:
    return [_compact(str(target["expr"])) for target in _targets(_panel(title))]


def _selectors(expr: str, metric: str) -> list[str]:
    """The label matchers of each use of one of `metric`'s series in a compacted query."""
    pattern = re.compile(rf"\b{metric}_(?:bucket|count|sum)(?:\{{(?P<labels>{LABELS})\}})?")
    return [match.group("labels") or "" for match in pattern.finditer(expr)]


def _all_selectors(title: str, metric: str) -> list[str]:
    selectors = [selector for expr in _exprs(title) for selector in _selectors(expr, metric)]
    assert selectors, f"panel {title!r} does not query {metric}"
    return selectors


def _grouping(match: re.Match[str]) -> frozenset[str]:
    """The labels of a `sum by (...)`, written before or after the summed expression."""
    labels = match.group("by") or match.group("by_after") or ""
    return frozenset(label for label in labels.split(",") if label)


@dataclass(frozen=True)
class Sum:
    grouping: frozenset[str]
    window: str


def _sums(title: str, function: str, series: str) -> list[Sum]:
    """Every `sum` of `function` (`rate` or `increase`) over `series` in the panel's queries."""
    pattern = re.compile(
        rf"sum(?:by\((?P<by>[^)]*)\))?\({function}\({series}(?:\{{{LABELS}\}})?"
        r"\[(?P<window>[^\]]+)\]\)\)(?:by\((?P<by_after>[^)]*)\))?"
    )
    return [
        Sum(_grouping(match), match.group("window"))
        for expr in _exprs(title)
        for match in pattern.finditer(expr)
    ]


@dataclass(frozen=True)
class Percentile:
    quantile: float
    grouping: frozenset[str]
    series: str
    labels: str
    window: str


def _percentiles(title: str) -> list[Percentile]:
    """Every `histogram_quantile` over a summed rate or increase of a bucket series."""
    pattern = re.compile(
        r"histogram_quantile\((?P<q>[0-9.]+),sum(?:by\((?P<by>[^)]*)\))?"
        rf"\((?:rate|increase)\((?P<series>\w+)(?:\{{(?P<labels>{LABELS})\}})?"
        r"\[(?P<window>[^\]]+)\]\)\)(?:by\((?P<by_after>[^)]*)\))?\)"
    )
    found = [
        Percentile(
            float(match.group("q")),
            _grouping(match),
            match.group("series"),
            match.group("labels") or "",
            match.group("window"),
        )
        for expr in _exprs(title)
        for match in pattern.finditer(expr)
    ]
    assert found, f"panel {title!r} computes no percentile from a summed bucket series"
    return found


def _datasource_uids(panel: dict[str, Any]) -> set[str]:
    uids = set()
    for holder in (panel, *_targets(panel)):
        datasource = holder.get("datasource")
        if isinstance(datasource, dict) and "uid" in datasource:
            uids.add(str(datasource["uid"]))
    return uids


def _tool_variable() -> dict[str, Any]:
    found = [
        variable
        for variable in _dashboard().get("templating", {}).get("list", [])
        if variable.get("name") == "tool"
    ]
    assert len(found) == 1, f"expected one variable named 'tool', found {len(found)}"
    return found[0]


def _variable_query(variable: dict[str, Any]) -> str:
    query = variable.get("query", "")
    if isinstance(query, dict):
        query = query.get("query", "")
    return _compact(str(query))


def _stacking(title: str) -> str:
    return str(
        _panel(title)
        .get("fieldConfig", {})
        .get("defaults", {})
        .get("custom", {})
        .get("stacking", {})
        .get("mode")
    )


def _readme() -> str:
    return README.read_text(encoding="utf-8")


# --- monitoring stack --------------------------------------------------------------------


# @spec TEL-042
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_stack_runs_the_all_in_one_image_at_a_pinned_version() -> None:
    tag = str(_stack_service()["image"]).removeprefix(f"{IMAGE}:")

    assert re.fullmatch(r"\d+(\.\d+)+", tag), f"the image tag {tag!r} is not a pinned version"


# @spec TEL-043
@pytest.mark.parametrize("port", ["4318", "4317", "3000"])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_stack_publishes_each_port_on_the_loopback_address_only(port: str) -> None:
    bindings = {
        (binding.host_ip, binding.published)
        for binding in _port_bindings()
        if binding.target == port
    }

    assert bindings == {("127.0.0.1", port)}


# @spec TEL-043
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_stack_publishes_no_port_beyond_the_loopback_address() -> None:
    exposed = [binding for binding in _port_bindings() if binding.host_ip != "127.0.0.1"]

    assert exposed == []


# @spec TEL-044
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_stack_keeps_its_stored_data_in_a_named_volume() -> None:
    named = set((_compose().get("volumes") or {}).keys())
    data_mounts = [mount for mount in _mounts() if mount.target == STORED_DATA]

    assert [(mount.kind, mount.source in named) for mount in data_mounts] == [("volume", True)]


def _provider_mount() -> Mount:
    found = [
        mount
        for mount in _mounts()
        if mount.kind == "bind" and _host_path(mount) == PROVIDER.resolve()
    ]
    assert len(found) == 1, f"expected {PROVIDER.name} mounted once, found {len(found)}"
    return found[0]


def _dashboard_mount() -> Mount:
    found = [
        mount
        for mount in _mounts()
        if mount.kind == "bind"
        and _host_path(mount) in (DASHBOARD.resolve(), DASHBOARD.parent.resolve())
    ]
    assert len(found) == 1, (
        f"expected the dashboard (or its folder) mounted once, found {len(found)}"
    )
    return found[0]


# @spec TEL-045
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_stack_mounts_the_dashboard_provider_into_grafanas_provisioning() -> None:
    mount = _provider_mount()

    assert (mount.target.parent, mount.target.suffix) == (GRAFANA_PROVISIONING, ".yaml")


# @spec TEL-045
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_dashboard_provider_points_grafana_at_the_mounted_dashboard() -> None:
    provider = yaml.safe_load(PROVIDER.read_text(encoding="utf-8"))
    paths = [PurePosixPath(entry["options"]["path"]) for entry in provider["providers"]]
    mounted = _dashboard_mount().target

    assert any(path == mounted or path in mounted.parents for path in paths), (
        f"no provider path {paths} reaches the mounted dashboard at {mounted}"
    )


# @spec TEL-045
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_dashboard_provider_reads_files() -> None:
    provider = yaml.safe_load(PROVIDER.read_text(encoding="utf-8"))

    assert {entry.get("type") for entry in provider["providers"]} == {"file"}


# @spec TEL-046
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_every_panel_queries_the_stacks_prometheus() -> None:
    off = {panel["title"]: _datasource_uids(panel) for panel in _panels() if panel.get("targets")}

    assert {title: uids for title, uids in off.items() if uids != {"prometheus"}} == {}


# @spec TEL-046
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_every_query_names_the_metrics_as_the_pinned_image_stores_them() -> None:
    named = {
        name
        for panel in _panels()
        for target in panel.get("targets", [])
        for name in re.findall(r"\b(?:goldfishing|http)_\w+", str(target.get("expr", "")))
        if not name.startswith(("http_route", "http_request", "http_response"))
    }

    assert named - STORED_METRICS == set()


# @spec TEL-047
@pytest.mark.parametrize(
    "instruction",
    [
        "docker compose -f monitoring/compose.yaml up -d",
        "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318",
        "http://localhost:3000",
    ],
    ids=["start the stack", "start the service pushing to it", "open the dashboard"],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_readme_says_how_to_watch_the_service(instruction: str) -> None:
    assert instruction in _readme()


# --- dashboard ---------------------------------------------------------------------------


# @spec TEL-048
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_dashboard_is_titled_mtg_goldfishing() -> None:
    assert _dashboard()["title"] == "MTG Goldfishing"


# @spec TEL-048
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_dashboard_refreshes_every_five_seconds() -> None:
    assert _dashboard()["refresh"] == "5s"


# @spec TEL-048
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_dashboard_opens_on_the_last_fifteen_minutes() -> None:
    assert _dashboard()["time"] == {"from": "now-15m", "to": "now"}


# @spec TEL-049
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_tool_variable_lists_the_tool_names_of_the_tool_call_metric() -> None:
    query = _variable_query(_tool_variable())

    assert re.fullmatch(
        rf"label_values\({TOOL_METRIC}_(bucket|count|sum)(\{{\}})?,tool_name\)", query
    ), f"the tool variable's query {query!r} is not every tool_name of {TOOL_METRIC}"


# @spec TEL-049
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_tool_variable_hides_no_tool_name() -> None:
    assert _tool_variable().get("regex", "") == ""


# @spec TEL-049
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_tool_variable_allows_several_tools_to_be_selected() -> None:
    assert _tool_variable()["multi"] is True


# @spec TEL-049
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_the_tool_variable_includes_every_tool_by_default() -> None:
    variable = _tool_variable()
    value = variable.get("current", {}).get("value")

    assert (variable.get("includeAll"), value in ("$__all", ["$__all"])) == (True, True)


# @spec TEL-049
@pytest.mark.parametrize("title", FILTERED_TOOL_PANELS)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_tool_panel_shows_only_the_selected_tools(title: str) -> None:
    unfiltered = [
        selector
        for selector in _all_selectors(title, TOOL_METRIC)
        if not TOOL_SELECTED.search(selector)
    ]

    assert unfiltered == []


# @spec TEL-050, TEL-051, TEL-052, TEL-053, TEL-055, TEL-056, TEL-057
@pytest.mark.parametrize(
    "title",
    [TOOL_LATENCY, CALLS_BY_STATUS, ERROR_RATE, WAIT_LATENCY, HTTP_LATENCY, HTTP_BY_STATUS_CODE],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_panel_over_time_is_a_time_series(title: str) -> None:
    assert _panel(title)["type"] == "timeseries"


# @spec TEL-051, TEL-054
@pytest.mark.parametrize("title", [LATENCY_BY_TOOL, CALLS_BY_TOOL_AND_STATUS])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_panel_over_the_selected_range_is_a_table(title: str) -> None:
    assert _panel(title)["type"] == "table"


# @spec TEL-051, TEL-054
@pytest.mark.parametrize("title", [LATENCY_BY_TOOL, CALLS_BY_TOOL_AND_STATUS])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_table_queries_once_at_the_end_of_the_selected_range(title: str) -> None:
    ranged = [
        target.get("refId")
        for target in _targets(_panel(title))
        if target.get("instant") is not True
    ]

    assert ranged == []


# @spec TEL-050, TEL-051, TEL-055, TEL-056
@pytest.mark.parametrize("title", [*TIME_SERIES_PERCENTILE_PANELS, *TABLE_PERCENTILE_PANELS])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_latency_panel_shows_the_p50_p95_and_p99(title: str) -> None:
    assert {percentile.quantile for percentile in _percentiles(title)} == PERCENTILES


# @spec TEL-050, TEL-051, TEL-055, TEL-056
@pytest.mark.parametrize(
    ("title", "series"),
    [
        (TOOL_LATENCY, f"{TOOL_METRIC}_bucket"),
        (LATENCY_BY_TOOL, f"{TOOL_METRIC}_bucket"),
        (WAIT_LATENCY, f"{TOOL_METRIC}_bucket"),
        (HTTP_LATENCY, f"{HTTP_METRIC}_bucket"),
    ],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_latency_panel_reads_its_instruments_bucket_series(title: str, series: str) -> None:
    assert {percentile.series for percentile in _percentiles(title)} == {series}


# @spec TEL-050, TEL-051, TEL-055, TEL-056
@pytest.mark.parametrize(
    ("title", "grouping"),
    [
        (TOOL_LATENCY, {"le"}),
        (LATENCY_BY_TOOL, {"le", "tool_name"}),
        (WAIT_LATENCY, {"le"}),
        (HTTP_LATENCY, {"le", "http_route"}),
    ],
    ids=["pooled across tools", "one row per tool", "wait alone", "one line per route"],
)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_latency_panel_groups_its_percentiles(title: str, grouping: set[str]) -> None:
    assert {percentile.grouping for percentile in _percentiles(title)} == {frozenset(grouping)}


# @spec TEL-050, TEL-053
@pytest.mark.parametrize("title", [TOOL_LATENCY, ERROR_RATE])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_panel_without_wait_leaves_wait_out(title: str) -> None:
    including_wait = [
        selector for selector in _all_selectors(title, TOOL_METRIC) if WAIT_EXCLUDED not in selector
    ]

    assert including_wait == []


# @spec TEL-051, TEL-052, TEL-054
@pytest.mark.parametrize("title", [LATENCY_BY_TOOL, CALLS_BY_STATUS, CALLS_BY_TOOL_AND_STATUS])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_panel_with_wait_keeps_wait_in(title: str) -> None:
    excluding = [selector for selector in _all_selectors(title, TOOL_METRIC) if "wait" in selector]

    assert excluding == []


# @spec TEL-052
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_tool_calls_by_status_shows_the_call_rate_for_each_status() -> None:
    sums = _sums(CALLS_BY_STATUS, "rate", f"{TOOL_METRIC}_count")

    assert [total.grouping for total in sums] == [{"tool_status"}]


# @spec TEL-052, TEL-057
@pytest.mark.parametrize("title", [CALLS_BY_STATUS, HTTP_BY_STATUS_CODE])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_rate_by_status_is_stacked(title: str) -> None:
    assert _stacking(title) == "normal"


# @spec TEL-053
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_tool_error_rate_counts_error_protocol_error_and_defect_as_errors() -> None:
    statuses = [
        set(match.split("|"))
        for selector in _all_selectors(ERROR_RATE, TOOL_METRIC)
        for match in re.findall(r'tool_status=~"\(?([A-Z_|]+)\)?"', selector)
    ]

    assert statuses == [{"ERROR", "PROTOCOL_ERROR", "DEFECT"}]


# @spec TEL-053
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_tool_error_rate_divides_the_error_calls_by_all_calls() -> None:
    shapes = [
        ("tool_status" in parts[0], "tool_status" in parts[1]) if len(parts) == 2 else None
        for parts in (expr.split("/") for expr in _exprs(ERROR_RATE))
    ]

    assert shapes == [(True, False)]


# @spec TEL-054
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_calls_by_tool_and_status_counts_the_calls_over_the_selected_range() -> None:
    sums = _sums(CALLS_BY_TOOL_AND_STATUS, "increase", f"{TOOL_METRIC}_count")

    assert [(total.grouping, total.window) for total in sums] == [
        ({"tool_name", "tool_status"}, "$__range")
    ]


# @spec TEL-054
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_calls_by_tool_and_status_has_a_row_per_tool_and_a_column_per_status() -> None:
    transformations = _panel(CALLS_BY_TOOL_AND_STATUS).get("transformations", [])
    matrix = any(
        step.get("id") == "groupingToMatrix"
        and step.get("options", {}).get("rowField") == "tool_name"
        and step.get("options", {}).get("columnField") == "tool_status"
        for step in transformations
    )
    labels_to_columns = any(
        step.get("id") == "labelsToFields"
        and step.get("options", {}).get("valueLabel") == "tool_status"
        for step in transformations
    )

    assert matrix or labels_to_columns, (
        f"no transformation pivots tool_status into columns: {transformations}"
    )


# @spec TEL-055
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_wait_latency_shows_only_wait() -> None:
    selectors = _all_selectors(WAIT_LATENCY, TOOL_METRIC)

    assert [WAIT_ONLY in selector for selector in selectors] == [True] * len(selectors)


# @spec TEL-055
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_wait_latency_ignores_the_tool_selection() -> None:
    exprs = _exprs(WAIT_LATENCY)

    assert [
        expr for expr in exprs if "$tool" in expr or "${tool}" in expr or "[[tool]]" in expr
    ] == []


# @spec TEL-057
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_http_requests_by_status_code_shows_the_request_rate_for_each_status_code() -> None:
    sums = _sums(HTTP_BY_STATUS_CODE, "rate", f"{HTTP_METRIC}_count")

    assert [total.grouping for total in sums] == [{"http_response_status_code"}]


# @spec TEL-057
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_http_requests_by_status_code_shows_a_request_without_one_as_none() -> None:
    pattern = re.compile(
        r'label_replace\(.*,"http_response_status_code","none","http_response_status_code","(\^?\$?)"\)$'
    )
    exprs = _exprs(HTTP_BY_STATUS_CODE)

    assert [bool(pattern.search(expr)) for expr in exprs] == [True]


# @spec TEL-058
@pytest.mark.parametrize("title", TIME_SERIES_PERCENTILE_PANELS)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_time_series_percentile_uses_a_rolling_one_minute_window(title: str) -> None:
    assert {percentile.window for percentile in _percentiles(title)} == {"1m"}


# @spec TEL-058
@pytest.mark.parametrize("title", TABLE_PERCENTILE_PANELS)
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_table_percentile_spans_the_selected_time_range(title: str) -> None:
    assert {percentile.window for percentile in _percentiles(title)} == {"$__range"}


# @spec TEL-058
@pytest.mark.parametrize("title", [*TIME_SERIES_PERCENTILE_PANELS, *TABLE_PERCENTILE_PANELS])
@pytest.mark.xfail(strict=True, reason="Written before the telemetry code (TEL)")
def test_a_percentile_sums_the_buckets_across_service_instances(title: str) -> None:
    kept_apart = {
        label for percentile in _percentiles(title) for label in percentile.grouping
    } & INSTANCE_LABELS

    assert kept_apart == set()

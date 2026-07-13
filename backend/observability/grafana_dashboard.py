"""Grafana dashboard configuration for trace correlation and operational metrics."""
import json


def create_dashboard_config() -> dict[str, object]:
    """Generate Grafana dashboard JSON for distributed tracing visualization.

    Includes panels for:
    - Trace execution timeline
    - Log-to-trace correlation
    - Exemplar-linked metrics
    - Sampling rate health
    - Span export metrics
    """

    dashboard = {
        "dashboard": {
            "title": "Distributed Tracing & Operational Metrics",
            "description": "Trace propagation, log correlation, exemplars, and sampling health",
            "tags": ["tracing", "observability", "distributed"],
            "timezone": "UTC",
            "refresh": "10s",
            "time": {"from": "now-1h", "to": "now"},
            "panels": [
                _create_trace_timeline_panel(),
                _create_log_correlation_panel(),
                _create_exemplar_panel(),
                _create_sampling_rate_panel(),
                _create_span_export_panel(),
                _create_error_rate_panel(),
            ],
        }
    }

    return dashboard


def _create_trace_timeline_panel() -> dict[str, object]:
    """Panel showing trace execution timeline with parent-child spans."""
    return {
        "id": 1,
        "title": "Trace Execution Timeline",
        "type": "trace",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
            {
                "datasource": "Jaeger",
                "queryType": "traceQuery",
            }
        ],
        "options": {
            "showSpanLines": True,
            "spanHeight": 40,
        },
        "description": "Distributed trace visualization showing parent-child span hierarchy",
    }


def _create_log_correlation_panel() -> dict[str, object]:
    """Panel showing logs linked to traces via trace_id."""
    return {
        "id": 2,
        "title": "Logs Correlated with Traces",
        "type": "logs",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
            {
                "datasource": "Loki",
                "expr": '{job="ship-it"} | json trace_id != "-"',
                "refId": "A",
            }
        ],
        "options": {
            "dedupStrategy": "none",
            "wrapLogMessage": False,
        },
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "hideFrom": {
                        "tooltip": False,
                        "viz": False,
                        "legend": False,
                    }
                }
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "trace_id"},
                    "properties": [
                        {
                            "id": "custom.links",
                            "value": [
                                {
                                    "title": "View in Jaeger",
                                    "url": "http://jaeger:16686/trace/${{trace_id}}",
                                    "targetBlank": True,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "description": "Logs with trace_id field linked to Jaeger traces",
    }


def _create_exemplar_panel() -> dict[str, object]:
    """Panel showing exemplar-linked metrics."""
    return {
        "id": 3,
        "title": "Exemplars: Metrics Linked to Traces",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
            {
                "datasource": "Prometheus",
                "expr": "rate(http_request_duration_seconds_bucket[5m])",
                "format": "heatmap",
                "legendFormat": "{{ method }} {{ path }}",
                "refId": "A",
            }
        ],
        "options": {
            "showExempars": True,
            "exemplarLinkColor": "#6173C3",
        },
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "links": [
                        {
                            "title": "Trace",
                            "url": "http://jaeger:16686/trace/${{exemplar_trace_id}}",
                            "targetBlank": True,
                        }
                    ]
                }
            }
        },
        "description": "Request latency distribution with exemplar links to individual traces",
    }


def _create_sampling_rate_panel() -> dict[str, object]:
    """Panel showing current sampling rate."""
    return {
        "id": 4,
        "title": "Sampling Rate & Health",
        "type": "stat",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
            {
                "datasource": "Prometheus",
                "expr": "otel_sampling_rate",
                "refId": "A",
            }
        ],
        "options": {
            "graphMode": "area",
            "orientation": "auto",
            "colorMode": "background",
            "textMode": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {"hideFrom": {"tooltip": False, "viz": False, "legend": False}},
                "unit": "percentunit",
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "otel_sampling_rate"},
                    "properties": [
                        {
                            "id": "thresholds",
                            "value": {
                                "mode": "percentage",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "yellow", "value": 0.05},
                                    {"color": "green", "value": 0.1},
                                ],
                            },
                        }
                    ],
                }
            ],
        },
        "description": "Current trace sampling rate (target: 0.1 = 10%)",
    }


def _create_span_export_panel() -> dict[str, object]:
    """Panel showing span export metrics."""
    return {
        "id": 5,
        "title": "Span Export Metrics",
        "type": "bargauge",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
        "targets": [
            {
                "datasource": "Prometheus",
                "expr": "rate(otel_span_exports_total[5m])",
                "legendFormat": "Exported",
                "refId": "A",
            },
            {
                "datasource": "Prometheus",
                "expr": "rate(otel_spans_dropped_total[5m])",
                "legendFormat": "Dropped",
                "refId": "B",
            },
        ],
        "options": {
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "background",
            "graphMode": "none",
        },
        "fieldConfig": {
            "defaults": {
                "unit": "ops",
                "color": {"mode": "palette-classic"},
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "Dropped"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
                    ],
                }
            ],
        },
        "description": "Spans exported vs dropped (per second)",
    }


def _create_error_rate_panel() -> dict[str, object]:
    """Panel showing error traces."""
    return {
        "id": 6,
        "title": "Error Traces (always sampled)",
        "type": "logs",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
        "targets": [
            {
                "datasource": "Jaeger",
                "queryType": "traceQuery",
                "tags": {"error": "true"},
            }
        ],
        "options": {
            "dedupStrategy": "none",
            "wrapLogMessage": False,
        },
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "links": [
                        {
                            "title": "View Full Trace",
                            "url": "http://jaeger:16686/trace/${{trace_id}}",
                            "targetBlank": True,
                        }
                    ]
                }
            }
        },
        "description": "Error spans captured in distributed traces",
    }


def save_dashboard_config(filepath: str) -> None:
    """Save dashboard configuration to JSON file."""
    config = create_dashboard_config()
    with open(filepath, "w") as f:
        json.dump(config, f, indent=2)

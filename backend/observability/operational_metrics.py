"""Operational metrics for distributed tracing — exemplars, sampling, health."""
from typing import Optional

try:
    from opentelemetry import metrics
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    MeterProvider = object  # type: ignore


# Counters and histograms for tracing operations
_span_export_counter = None
_span_drop_counter = None
_sampling_rate_gauge = None
_exemplar_registration_counter = None


def setup_operational_metrics(prometheus_enabled: bool = False) -> Optional[MeterProvider]:
    """Initialize metrics for tracing operations.

    If prometheus_enabled=True, returns a MeterProvider with PrometheusMetricReader
    for metrics scraping. Otherwise uses InMemoryMetricReader for testing.
    """
    if not _OTEL_AVAILABLE:
        return None

    reader = PrometheusMetricReader() if prometheus_enabled else InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter(__name__)

    global _span_export_counter, _span_drop_counter, _sampling_rate_gauge, _exemplar_registration_counter

    _span_export_counter = meter.create_counter(
        "otel_span_exports_total",
        description="Total spans exported",
        unit="1",
    )

    _span_drop_counter = meter.create_counter(
        "otel_spans_dropped_total",
        description="Total spans dropped due to buffer full or sampling",
        unit="1",
    )

    _sampling_rate_gauge = meter.create_gauge(
        "otel_sampling_rate",
        description="Current sampling rate (0.0 to 1.0)",
        unit="1",
    )

    _exemplar_registration_counter = meter.create_counter(
        "otel_exemplars_registered_total",
        description="Total exemplars registered (trace-to-metric correlation)",
        unit="1",
    )

    return provider


def record_span_exported(count: int = 1, attributes: dict = None) -> None:
    """Record that spans were exported successfully."""
    if _span_export_counter:
        _span_export_counter.add(count, attributes or {})


def record_span_dropped(count: int = 1, reason: str = "unknown") -> None:
    """Record spans dropped during export."""
    if _span_drop_counter:
        _span_drop_counter.add(count, {"reason": reason})


def set_sampling_rate(rate: float) -> None:
    """Update current sampling rate (0.0 to 1.0)."""
    if _sampling_rate_gauge:
        _sampling_rate_gauge.record(rate)


def record_exemplar_registration(trace_id: str, span_id: str, metric_name: str) -> None:
    """Record exemplar registration for trace-to-metric correlation."""
    if _exemplar_registration_counter:
        _exemplar_registration_counter.add(
            1,
            {
                "trace_id": trace_id[:8],  # First 8 chars for readability
                "metric": metric_name,
            }
        )


class ExemplarStorage:
    """In-memory exemplar storage for linking traces to metrics.

    Exemplars are (trace_id, span_id) tuples that link a specific span
    to the metric value it produced. Used for Grafana trace correlation.
    """

    def __init__(self, max_exemplars: int = 100):
        self.max_exemplars = max_exemplars
        self.exemplars: dict[str, list[dict]] = {}  # metric_name -> [exemplars]

    def add_exemplar(self, metric_name: str, trace_id: str, span_id: str, value: float) -> None:
        """Add exemplar (trace ID + value) to metric."""
        if metric_name not in self.exemplars:
            self.exemplars[metric_name] = []

        exemplar = {
            "trace_id": trace_id,
            "span_id": span_id,
            "value": value,
        }

        exemplars_list = self.exemplars[metric_name]
        exemplars_list.append(exemplar)

        if len(exemplars_list) > self.max_exemplars:
            exemplars_list.pop(0)

        record_exemplar_registration(trace_id, span_id, metric_name)

    def get_exemplars(self, metric_name: str) -> list[dict]:
        """Get exemplars for a metric (for Grafana dashboard queries)."""
        return self.exemplars.get(metric_name, [])


# Global exemplar storage
_exemplar_storage = ExemplarStorage()


def get_exemplar_storage() -> ExemplarStorage:
    """Get global exemplar storage instance."""
    return _exemplar_storage

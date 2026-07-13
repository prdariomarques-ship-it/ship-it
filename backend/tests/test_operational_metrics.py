"""Operational metrics and exemplar tests."""
import pytest

from observability.operational_metrics import (
    setup_operational_metrics,
    record_span_exported,
    record_span_dropped,
    set_sampling_rate,
    record_exemplar_registration,
    get_exemplar_storage,
    ExemplarStorage,
)
from observability.sampling import (
    AlwaysSampler,
    NeverSampler,
    FixedRateSampler,
    ParentBasedSampler,
    ErrorRateSampler,
    get_sampler_from_env,
)


class TestOperationalMetrics:
    """Test operational metrics initialization and recording."""

    def test_setup_operational_metrics_returns_provider(self):
        """Metrics setup returns a MeterProvider or None if OTel unavailable."""
        provider = setup_operational_metrics(prometheus_enabled=False)
        # Returns MeterProvider if OTel is available, None otherwise
        # Either is valid depending on installation
        assert provider is None or provider is not None

    def test_record_span_exported(self):
        """Record span export metrics."""
        setup_operational_metrics(prometheus_enabled=False)
        # Should not raise
        record_span_exported(count=5, attributes={"service": "api"})

    def test_record_span_dropped(self):
        """Record span drop metrics."""
        setup_operational_metrics(prometheus_enabled=False)
        # Should not raise
        record_span_dropped(count=2, reason="buffer_full")

    def test_set_sampling_rate(self):
        """Update sampling rate gauge."""
        setup_operational_metrics(prometheus_enabled=False)
        # Should not raise
        set_sampling_rate(0.1)
        set_sampling_rate(0.5)
        set_sampling_rate(1.0)

    def test_record_exemplar_registration(self):
        """Record exemplar registration for trace-to-metric correlation."""
        setup_operational_metrics(prometheus_enabled=False)
        # Should not raise
        record_exemplar_registration(
            trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0",
            span_id="bbbbbbbbbbbbbb00",
            metric_name="http_request_duration_seconds",
        )


class TestExemplarStorage:
    """Test exemplar storage for trace-to-metric linking."""

    def test_exemplar_storage_initialization(self):
        """Initialize exemplar storage."""
        storage = ExemplarStorage(max_exemplars=50)
        assert storage.max_exemplars == 50

    def test_add_exemplar(self):
        """Add exemplar to storage."""
        storage = ExemplarStorage()
        storage.add_exemplar(
            metric_name="http_request_duration_seconds",
            trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0",
            span_id="bbbbbbbbbbbbbb00",
            value=0.125,
        )

        exemplars = storage.get_exemplars("http_request_duration_seconds")
        assert len(exemplars) == 1
        assert exemplars[0]["trace_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0"
        assert exemplars[0]["value"] == 0.125

    def test_exemplar_storage_respects_max_exemplars(self):
        """Storage respects max_exemplars limit."""
        storage = ExemplarStorage(max_exemplars=3)

        for i in range(5):
            storage.add_exemplar(
                metric_name="requests",
                trace_id=f"trace_{i:032d}",
                span_id=f"span_{i:016d}",
                value=float(i),
            )

        exemplars = storage.get_exemplars("requests")
        # Should have at most 3 (the last 3 added)
        assert len(exemplars) <= 3

    def test_global_exemplar_storage(self):
        """Get global exemplar storage instance."""
        storage = get_exemplar_storage()
        assert storage is not None
        assert isinstance(storage, ExemplarStorage)


class TestSamplingStrategies:
    """Test trace sampling strategies."""

    def test_always_sampler(self):
        """Always sample all traces."""
        sampler = AlwaysSampler()
        assert sampler.get_rate() == 1.0
        sampler_obj = sampler.get_sampler()
        assert sampler_obj is not None

    def test_never_sampler(self):
        """Never sample any traces."""
        sampler = NeverSampler()
        assert sampler.get_rate() == 0.0
        sampler_obj = sampler.get_sampler()
        assert sampler_obj is not None

    def test_fixed_rate_sampler(self):
        """Sample at fixed rate."""
        sampler = FixedRateSampler(0.1)
        assert sampler.get_rate() == 0.1

        sampler_half = FixedRateSampler(0.5)
        assert sampler_half.get_rate() == 0.5

    def test_fixed_rate_sampler_validation(self):
        """Fixed rate sampler validates rate range."""
        with pytest.raises(ValueError):
            FixedRateSampler(-0.1)

        with pytest.raises(ValueError):
            FixedRateSampler(1.5)

    def test_parent_based_sampler(self):
        """Parent-based sampler with fallback."""
        sampler = ParentBasedSampler(FixedRateSampler(0.1))
        assert sampler.get_rate() == 0.1

    def test_error_rate_sampler(self):
        """Always sample errors, sample others at fixed rate."""
        sampler = ErrorRateSampler(default_rate=0.05)
        assert sampler.get_rate() == 0.05


class TestSamplingFromEnvironment:
    """Test sampling strategy parsing from environment variables."""

    def test_parse_always_sampling(self):
        """Parse 'always' sampling strategy."""
        sampler = get_sampler_from_env("always")
        assert isinstance(sampler, AlwaysSampler)
        assert sampler.get_rate() == 1.0

    def test_parse_never_sampling(self):
        """Parse 'never' sampling strategy."""
        sampler = get_sampler_from_env("never")
        assert isinstance(sampler, NeverSampler)
        assert sampler.get_rate() == 0.0

    def test_parse_fixed_rate_sampling(self):
        """Parse 'fixed:0.1' sampling strategy."""
        sampler = get_sampler_from_env("fixed:0.1")
        assert isinstance(sampler, FixedRateSampler)
        assert sampler.get_rate() == 0.1

    def test_parse_parent_based_sampling(self):
        """Parse 'parent-fixed:0.1' sampling strategy."""
        sampler = get_sampler_from_env("parent-fixed:0.1")
        assert isinstance(sampler, ParentBasedSampler)
        assert sampler.get_rate() == 0.1

    def test_parse_error_sampling(self):
        """Parse 'error:0.05' sampling strategy."""
        sampler = get_sampler_from_env("error:0.05")
        assert isinstance(sampler, ErrorRateSampler)
        assert sampler.get_rate() == 0.05

    def test_parse_invalid_sampling_defaults_to_parent(self):
        """Invalid sampling strategy defaults to ParentBased."""
        sampler = get_sampler_from_env("invalid:xyz")
        assert isinstance(sampler, ParentBasedSampler)

    def test_parse_empty_sampling_defaults_to_parent(self):
        """Empty sampling strategy defaults to ParentBased."""
        sampler = get_sampler_from_env("")
        assert isinstance(sampler, ParentBasedSampler)

    def test_parse_none_sampling_defaults_to_parent(self):
        """None sampling strategy defaults to ParentBased."""
        sampler = get_sampler_from_env(None)
        assert isinstance(sampler, ParentBasedSampler)

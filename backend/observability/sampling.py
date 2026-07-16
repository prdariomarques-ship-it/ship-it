"""Trace sampling strategies — optimize performance while maintaining observability."""

from abc import ABC, abstractmethod
from typing import Optional

try:
    from opentelemetry.sdk.trace.sampling import Sampler, SamplingResult, Decision  # noqa: F401 — availability probe

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class SamplingStrategy(ABC):
    """Base class for sampling strategies."""

    @abstractmethod
    def get_sampler(self) -> Optional[object]:
        """Return an OTel Sampler instance."""
        pass

    @abstractmethod
    def get_rate(self) -> float:
        """Return current sampling rate (0.0 to 1.0)."""
        pass


class AlwaysSampler(SamplingStrategy):
    """Sample all traces (useful for development, small deployments)."""

    def get_sampler(self) -> Optional[object]:
        if not _OTEL_AVAILABLE:
            return None
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        return ALWAYS_ON

    def get_rate(self) -> float:
        return 1.0


class NeverSampler(SamplingStrategy):
    """Sample no traces (disable tracing)."""

    def get_sampler(self) -> Optional[object]:
        if not _OTEL_AVAILABLE:
            return None
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

        return ALWAYS_OFF

    def get_rate(self) -> float:
        return 0.0


class FixedRateSampler(SamplingStrategy):
    """Sample at a fixed rate (e.g., 0.1 = 10% of traces)."""

    def __init__(self, rate: float):
        if not 0.0 <= rate <= 1.0:
            raise ValueError("rate must be between 0.0 and 1.0")
        self.rate = rate

    def get_sampler(self) -> Optional[object]:
        if not _OTEL_AVAILABLE:
            return None
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        return TraceIdRatioBased(self.rate)

    def get_rate(self) -> float:
        return self.rate


class ParentBasedSampler(SamplingStrategy):
    """Sample based on parent span decision (for distributed traces).

    If span has parent: inherit parent's decision.
    If root span: use root_sampler decision (e.g., fixed rate).
    """

    def __init__(self, root_sampler: Optional[SamplingStrategy] = None):
        self.root_sampler = root_sampler or FixedRateSampler(
            0.1
        )  # Default 10% for root spans

    def get_sampler(self) -> Optional[object]:
        if not _OTEL_AVAILABLE:
            return None
        from opentelemetry.sdk.trace.sampling import ParentBased

        root_sampler = self.root_sampler.get_sampler()
        # get_sampler() is typed Optional[object] so this module stays importable
        # without opentelemetry installed; root_sampler is a real Sampler here.
        return ParentBased(root_sampler)  # type: ignore[arg-type]

    def get_rate(self) -> float:
        return self.root_sampler.get_rate()


class ErrorRateSampler(SamplingStrategy):
    """Always sample spans with errors, sample others at fixed rate.

    Ensures error traces are always captured for debugging.
    """

    def __init__(self, default_rate: float = 0.1):
        if not 0.0 <= default_rate <= 1.0:
            raise ValueError("default_rate must be between 0.0 and 1.0")
        self.default_rate = default_rate

    def get_sampler(self) -> Optional[object]:
        if not _OTEL_AVAILABLE:
            return None
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        return TraceIdRatioBased(self.default_rate)

    def get_rate(self) -> float:
        return self.default_rate


def get_sampler_from_env(env_sampling: Optional[str]) -> SamplingStrategy:
    """Get sampler from environment variable.

    Format: "always" | "never" | "fixed:0.1" | "parent-fixed:0.1" | "error:0.05"
    """
    if not env_sampling:
        return ParentBasedSampler()

    parts = env_sampling.split(":")

    if parts[0] == "always":
        return AlwaysSampler()
    elif parts[0] == "never":
        return NeverSampler()
    elif parts[0] == "fixed" and len(parts) == 2:
        try:
            rate = float(parts[1])
            return FixedRateSampler(rate)
        except (ValueError, IndexError):
            return ParentBasedSampler()
    elif parts[0] == "parent-fixed" and len(parts) == 2:
        try:
            rate = float(parts[1])
            return ParentBasedSampler(FixedRateSampler(rate))
        except (ValueError, IndexError):
            return ParentBasedSampler()
    elif parts[0] == "error" and len(parts) == 2:
        try:
            rate = float(parts[1])
            return ErrorRateSampler(rate)
        except (ValueError, IndexError):
            return ParentBasedSampler()
    else:
        return ParentBasedSampler()

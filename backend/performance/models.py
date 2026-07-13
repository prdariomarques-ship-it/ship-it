"""Performance optimization models and schemas.

Provides:
- Performance metrics storage
- Cache statistics schemas
- SLA compliance tracking
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CacheStatsSchema(BaseModel):
    """Cache statistics snapshot."""

    hits: int = Field(ge=0, description="Number of cache hits")
    misses: int = Field(ge=0, description="Number of cache misses")
    evictions: int = Field(ge=0, description="Number of cache evictions")
    sets: int = Field(ge=0, description="Number of cache sets")
    deletes: int = Field(ge=0, description="Number of cache deletes")
    hit_ratio: float = Field(ge=0.0, le=1.0, description="Cache hit ratio (0-1)")

    class Config:
        json_schema_extra = {
            "example": {
                "hits": 1500,
                "misses": 500,
                "evictions": 20,
                "sets": 2000,
                "deletes": 100,
                "hit_ratio": 0.75,
            }
        }


class PerformanceMetricsSchema(BaseModel):
    """Request-level performance metrics."""

    request_id: str
    endpoint: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float = Field(ge=0, description="Total request duration")
    cache_hits: int = Field(ge=0)
    cache_misses: int = Field(ge=0)
    cache_hit_ratio: float = Field(ge=0.0, le=1.0)
    db_query_count: int = Field(ge=0)
    db_query_duration_ms: float = Field(ge=0)
    sla_compliant: bool = Field(description="Whether request met SLA (p95 < 200ms)")
    status_code: int = Field(ge=100, le=599)

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-123",
                "endpoint": "GET /api/agents",
                "duration_ms": 145.5,
                "cache_hits": 3,
                "cache_misses": 1,
                "cache_hit_ratio": 0.75,
                "db_query_count": 2,
                "db_query_duration_ms": 45.0,
                "sla_compliant": True,
                "status_code": 200,
            }
        }


class IndexRecommendationSchema(BaseModel):
    """Database index recommendation."""

    table: str
    columns: List[str]
    reason: str
    priority: str = Field(description="low, medium, or high")
    estimated_benefit: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "table": "jobs",
                "columns": ["status", "created_at"],
                "reason": "Composite index for status filtering + time sorting",
                "priority": "high",
                "estimated_benefit": "40-50% query time reduction",
            }
        }


class SLAComplianceSchema(BaseModel):
    """SLA compliance metrics."""

    period_start: datetime
    period_end: datetime
    total_requests: int = Field(ge=0)
    compliant_requests: int = Field(ge=0)
    sla_compliance_percentage: float = Field(ge=0.0, le=100.0)
    p50_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    p99_latency_ms: float = Field(ge=0)
    max_latency_ms: float = Field(ge=0)
    average_latency_ms: float = Field(ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "period_start": "2026-07-13T00:00:00Z",
                "period_end": "2026-07-13T23:59:59Z",
                "total_requests": 10000,
                "compliant_requests": 9800,
                "sla_compliance_percentage": 98.0,
                "p50_latency_ms": 50,
                "p95_latency_ms": 180,
                "p99_latency_ms": 250,
                "max_latency_ms": 1500,
                "average_latency_ms": 75,
            }
        }


class QueryOptimizationSchema(BaseModel):
    """Query optimization recommendations."""

    endpoint: str
    query_count_before: int = Field(description="Query count before optimization")
    query_count_after: int = Field(description="Query count after optimization")
    reduction_percentage: float = Field(description="Percentage reduction")
    primary_issue: str = Field(description="N+1, missing eager loading, etc.")
    recommendation: str = Field(description="Optimization recommendation")
    estimated_benefit: str = Field(description="Expected performance improvement")

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "GET /api/agents",
                "query_count_before": 51,
                "query_count_after": 2,
                "reduction_percentage": 96,
                "primary_issue": "N+1 query pattern on agent relationships",
                "recommendation": "Use eager loading with joinedload on User relationship",
                "estimated_benefit": "Query time reduced from 500ms to 50ms (~10x speedup)",
            }
        }


class BundleSizeAnalysisSchema(BaseModel):
    """Frontend bundle size analysis."""

    total_size_bytes: int = Field(description="Total bundle size")
    gzipped_size_bytes: int = Field(description="Gzipped bundle size")
    chunks: List[Dict[str, Any]] = Field(description="List of chunk sizes")
    largest_dependencies: List[str] = Field(description="Top 5 largest dependencies")
    optimization_opportunities: List[str] = Field(description="Recommended optimizations")

    class Config:
        json_schema_extra = {
            "example": {
                "total_size_bytes": 850000,
                "gzipped_size_bytes": 450000,
                "chunks": [
                    {"name": "main.js", "size": 300000},
                    {"name": "vendor.js", "size": 400000},
                ],
                "largest_dependencies": ["react", "react-dom", "lodash"],
                "optimization_opportunities": [
                    "Remove unused lodash functions",
                    "Split large modal components",
                ],
            }
        }


class PerformanceReportSchema(BaseModel):
    """Comprehensive performance report."""

    period: str = Field(description="Report period (e.g., 'Daily', 'Weekly')")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cache_metrics: CacheStatsSchema
    sla_compliance: SLAComplianceSchema
    database_metrics: Dict[str, Any]
    frontend_metrics: Dict[str, Any]
    top_slow_endpoints: List[Dict[str, Any]] = Field(description="Slowest endpoints")
    recommendations: List[str] = Field(description="Performance optimization recommendations")

    class Config:
        json_schema_extra = {
            "example": {
                "period": "daily",
                "cache_metrics": {
                    "hits": 15000,
                    "misses": 5000,
                    "hit_ratio": 0.75,
                },
                "sla_compliance": {
                    "total_requests": 20000,
                    "compliant_requests": 19600,
                    "sla_compliance_percentage": 98.0,
                },
                "recommendations": [
                    "Increase cache TTL for user list endpoint (20% hit ratio)",
                    "Add index on jobs.status column (100+ scans daily)",
                ],
            }
        }

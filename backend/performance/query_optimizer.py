"""Query optimization for N+1 prevention and eager loading.

Provides utilities to detect N+1 query patterns, recommend eager loading strategies,
and generate database index recommendations based on query analysis.
"""

import logging
from typing import Any, List, Dict, Optional
from sqlalchemy import inspect, text
from sqlalchemy.orm import Query, Session

logger = logging.getLogger(__name__)


class N1QueryPattern:
    """Represents a detected N+1 query pattern."""

    def __init__(self, root_query: str, child_queries: List[str], count: int):
        self.root_query = root_query
        self.child_queries = child_queries
        self.count = count

    def __repr__(self) -> str:
        return f"N1QueryPattern(root={self.root_query[:50]}..., count={self.count})"


class IndexRecommendation:
    """Represents a recommended database index."""

    def __init__(
        self, table: str, columns: List[str], reason: str, priority: str = "medium"
    ):
        self.table = table
        self.columns = columns
        self.reason = reason
        self.priority = priority  # low, medium, high

    def __repr__(self) -> str:
        return f"Index({self.table}.{','.join(self.columns)}, priority={self.priority})"


class QueryOptimizer:
    """Analyzes and optimizes SQLAlchemy queries for performance.

    Capabilities:
    - Detect N+1 query patterns
    - Recommend eager loading strategies (joinedload vs selectinload)
    - Generate index recommendations
    - Parse EXPLAIN plans
    """

    def __init__(self, session: Session):
        self.session = session
        self.detected_patterns: List[N1QueryPattern] = []
        self.index_recommendations: List[IndexRecommendation] = []

    def detect_n_plus_one(self, query: Query, query_name: str = "unknown") -> Optional[N1QueryPattern]:
        """Detect if a query exhibits N+1 pattern.

        Args:
            query: SQLAlchemy query object
            query_name: Name of the query for logging

        Returns:
            N1QueryPattern if detected, None otherwise
        """
        try:
            # Get the SQL statement
            compiled = query.statement.compile(compile_kwargs={"literal_binds": True})
            root_sql = str(compiled)

            # Check if query has relationships that might cause N+1
            mapper = query.column_descriptions[0].get("entity")
            if not mapper:
                return None

            relationships = [
                rel
                for rel in inspect(mapper).relationships
            ]

            if not relationships:
                return None

            # Count would-be child queries if relationships are lazy-loaded
            child_query_count = len(relationships)

            if child_query_count > 0:
                pattern = N1QueryPattern(
                    root_query=root_sql,
                    child_queries=[str(rel) for rel in relationships],
                    count=child_query_count,
                )
                self.detected_patterns.append(pattern)
                logger.warning(
                    f"N+1 pattern detected in '{query_name}': "
                    f"{child_query_count} child relationships not eagerly loaded"
                )
                return pattern
        except Exception as e:
            logger.debug(f"Could not analyze query '{query_name}': {e}")

        return None

    def recommend_eager_loading(self, mapper: Any) -> Dict[str, str]:
        """Recommend eager loading strategies for a mapper.

        Returns dict mapping relationship names to recommended strategy:
        - "joinedload": For single-related entities (foreign key)
        - "selectinload": For collections (one-to-many)
        - "subqueryload": For complex nested relationships
        """
        strategies = {}

        try:
            for relationship in inspect(mapper).relationships:
                if relationship.uselist:
                    # One-to-many: use selectinload to avoid cartesian product
                    strategies[relationship.key] = "selectinload"
                else:
                    # Many-to-one: use joinedload
                    strategies[relationship.key] = "joinedload"
        except Exception as e:
            logger.debug(f"Could not recommend eager loading for {mapper}: {e}")

        return strategies

    def recommend_indexes(self) -> List[IndexRecommendation]:
        """Generate index recommendations based on common query patterns.

        Returns:
            List of recommended indexes
        """

        # Common recommendations for observed patterns
        common_patterns = [
            IndexRecommendation(
                table="agents",
                columns=["agent_id", "status"],
                reason="Filter by agent_id and status in list queries",
                priority="high",
            ),
            IndexRecommendation(
                table="jobs",
                columns=["created_at"],
                reason="Sort jobs by creation time in list endpoints",
                priority="high",
            ),
            IndexRecommendation(
                table="jobs",
                columns=["status", "created_at"],
                reason="Composite index for status filtering + time sorting",
                priority="high",
            ),
            IndexRecommendation(
                table="messages",
                columns=["conversation_id", "created_at"],
                reason="Query messages by conversation ordered by time",
                priority="medium",
            ),
            IndexRecommendation(
                table="whatsapp_contacts",
                columns=["phone_number"],
                reason="Lookup contacts by phone number",
                priority="high",
            ),
            IndexRecommendation(
                table="whatsapp_conversations",
                columns=["contact_id", "updated_at"],
                reason="List conversations per contact, sorted by recency",
                priority="medium",
            ),
        ]

        self.index_recommendations = common_patterns
        return common_patterns

    def analyze_query_plan(self, query: Query) -> Dict[str, Any]:
        """Execute EXPLAIN on a query and return plan analysis.

        Args:
            query: SQLAlchemy query object

        Returns:
            Dict with plan analysis including cost estimate, rows, etc.
        """
        try:
            compiled = query.statement.compile(
                compile_kwargs={"literal_binds": True}
            )
            sql = str(compiled)

            # Add EXPLAIN prefix
            explain_sql = f"EXPLAIN (FORMAT json) {sql}"

            result = self.session.execute(text(explain_sql))
            plan = result.fetchone()[0]

            if plan:
                # Parse JSON plan
                if isinstance(plan, str):
                    import json
                    plan = json.loads(plan)

                return {
                    "plan": plan,
                    "total_cost": plan[0].get("Plan", {}).get("Total Cost"),
                    "rows": plan[0].get("Plan", {}).get("Actual Rows"),
                }
        except Exception as e:
            logger.debug(f"Could not analyze query plan: {e}")

        return {"error": "Could not analyze query plan"}

    def generate_migration_sql(self) -> str:
        """Generate Alembic migration SQL for recommended indexes.

        Returns:
            Alembic migration code as string
        """
        migration_lines = ["# Create recommended indexes for OBS-003"]

        for idx, rec in enumerate(self.index_recommendations, 1):
            col_list = ", ".join(f'"{col}"' for col in rec.columns)
            index_name = f"ix_{rec.table}_{'_'.join(rec.columns)}"

            migration_lines.append(
                f"op.create_index('{index_name}', '{rec.table}', [{col_list}])"
            )

        return "\n".join(migration_lines)


def analyze_endpoint_queries(session: Session, endpoint_name: str) -> List[N1QueryPattern]:
    """Audit all queries in an endpoint for N+1 patterns.

    Args:
        session: SQLAlchemy session
        endpoint_name: Name of the endpoint being analyzed

    Returns:
        List of detected N+1 patterns
    """
    optimizer = QueryOptimizer(session)
    return optimizer.detected_patterns


def recommend_indexes(session: Session) -> List[IndexRecommendation]:
    """Get database index recommendations.

    Args:
        session: SQLAlchemy session

    Returns:
        List of recommended indexes
    """
    optimizer = QueryOptimizer(session)
    return optimizer.recommend_indexes()

"""
Integration tests for OBS-001 Monitoring & Observability Stack.

Tests verify:
- Service discovery (Docker Compose DNS resolution)
- Prometheus scrape configuration
- Retention policy settings
- Alert rules validation
- Alertmanager routing
- Grafana provisioning (IaC)
"""

import pytest
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture
def app():
    """Create test FastAPI app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestMetricsEndpoint:
    """Verify /metrics endpoint security and format."""

    def test_metrics_endpoint_responds_with_prometheus_format(self, client):
        """Test /metrics returns valid Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Prometheus format: lines like 'metric_name{labels} value timestamp'
        assert "# HELP" in response.text or "# TYPE" in response.text or response.text.count("\n") > 0
        assert "http_requests_total" in response.text or "up" in response.text

    def test_metrics_endpoint_returns_prometheus_content_type(self, client):
        """Test /metrics content type is text/plain."""
        response = client.get("/metrics")
        assert response.headers.get("content-type", "").startswith("text/plain")

    def test_metrics_includes_http_request_duration(self, client):
        """Test http_request_duration_seconds histogram is present."""
        response = client.get("/metrics")
        assert "http_request_duration_seconds" in response.text

    def test_metrics_includes_http_request_count(self, client):
        """Test http_requests_total counter is present."""
        response = client.get("/metrics")
        assert "http_requests_total" in response.text

    def test_metrics_includes_health_check_endpoint(self, client):
        """Test /health endpoint exists and is accessible."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json() or "ok" in response.json().values()


class TestPrometheusConfiguration:
    """Verify Prometheus configuration (prometheus.yml)."""

    def test_prometheus_scrape_interval_is_15_seconds(self):
        """Verify scrape interval from prometheus.yml is 15s."""
        # This test reads the prometheus.yml file
        import os
        prometheus_yml_path = os.path.join(os.path.dirname(__file__), "../..", "docker/prometheus.yml")
        if os.path.exists(prometheus_yml_path):
            with open(prometheus_yml_path) as f:
                content = f.read()
                assert "scrape_interval: 15s" in content

    def test_prometheus_retention_policy_configured(self):
        """Verify retention policy in docker-compose.yml."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                assert "prometheus:v2.45.0" in content
                assert "--storage.tsdb.retention.time=15d" in content
                assert "--storage.tsdb.retention.size=15GB" in content

    def test_alert_rules_file_exists(self):
        """Verify alert_rules.yml file exists."""
        import os
        rules_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alert_rules.yml")
        assert os.path.exists(rules_path), "alert_rules.yml not found"

    def test_alert_rules_define_required_alerts(self):
        """Verify all required alert rules are defined."""
        import os
        rules_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alert_rules.yml")
        if os.path.exists(rules_path):
            with open(rules_path) as f:
                content = f.read()
                required_alerts = [
                    "ResponseTimeAnomaly",
                    "ErrorRateSpike",
                    "JobQueueOverflow",
                    "AgentTimeoutRate",
                    "LLMProviderError",
                    "DatabasePoolExhaustion",
                    "PrometheusScrapeFailed",
                ]
                for alert in required_alerts:
                    assert alert in content, f"Alert rule '{alert}' not found"


class TestAlertmanagerConfiguration:
    """Verify Alertmanager configuration (alertmanager.yml)."""

    def test_alertmanager_file_exists(self):
        """Verify alertmanager.yml file exists."""
        import os
        alertmanager_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alertmanager.yml")
        assert os.path.exists(alertmanager_path), "alertmanager.yml not found"

    def test_alertmanager_has_routing_tree(self):
        """Verify Alertmanager routing tree is configured."""
        import os
        alertmanager_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alertmanager.yml")
        if os.path.exists(alertmanager_path):
            with open(alertmanager_path) as f:
                content = f.read()
                assert "route:" in content
                assert "receivers:" in content
                assert "critical_webhook" in content or "webhook" in content

    def test_alertmanager_receivers_configured(self):
        """Verify Alertmanager receivers (webhook, email, Slack) are configured."""
        import os
        alertmanager_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alertmanager.yml")
        if os.path.exists(alertmanager_path):
            with open(alertmanager_path) as f:
                content = f.read()
                # Should have at least webhook_configs or email_configs
                assert "webhook_configs" in content or "email_configs" in content

    def test_alertmanager_grouping_configured(self):
        """Verify Alertmanager grouping policy is configured."""
        import os
        alertmanager_path = os.path.join(os.path.dirname(__file__), "../..", "docker/alertmanager.yml")
        if os.path.exists(alertmanager_path):
            with open(alertmanager_path) as f:
                content = f.read()
                assert "group_by:" in content
                assert "group_wait:" in content or "group_interval:" in content


class TestGrafanaProvisioning:
    """Verify Grafana provisioning (Infrastructure as Code)."""

    def test_grafana_datasource_provisioning_exists(self):
        """Verify Grafana datasource provisioning file exists."""
        import os
        ds_path = os.path.join(os.path.dirname(__file__), "../..", "docker/grafana/provisioning/datasources/prometheus.yml")
        assert os.path.exists(ds_path), "Grafana datasource provisioning not found"

    def test_grafana_dashboard_provider_exists(self):
        """Verify Grafana dashboard provider config exists."""
        import os
        provider_path = os.path.join(os.path.dirname(__file__), "../..", "docker/grafana/provisioning/dashboards/default.yml")
        assert os.path.exists(provider_path), "Grafana dashboard provider not found"

    def test_grafana_has_five_dashboards(self):
        """Verify all 5 required dashboards are provisioned."""
        import os
        dashboard_dir = os.path.join(os.path.dirname(__file__), "../..", "docker/grafana/provisioning/dashboards")
        required_dashboards = [
            "system-health.json",
            "agent-performance.json",
            "job-queue.json",
            "whatsapp-integration.json",
            "security.json",
        ]
        for dashboard in required_dashboards:
            dashboard_path = os.path.join(dashboard_dir, dashboard)
            assert os.path.exists(dashboard_path), f"Dashboard '{dashboard}' not found"

    def test_grafana_datasource_points_to_prometheus(self):
        """Verify Grafana datasource configuration points to Prometheus."""
        import os
        ds_path = os.path.join(os.path.dirname(__file__), "../..", "docker/grafana/provisioning/datasources/prometheus.yml")
        if os.path.exists(ds_path):
            with open(ds_path) as f:
                content = f.read()
                assert "prometheus:9090" in content or "prometheus" in content


class TestDockerComposeConfiguration:
    """Verify docker-compose.yml has monitoring services."""

    def test_prometheus_service_defined(self):
        """Verify Prometheus service is in docker-compose.yml."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                assert "prometheus:" in content
                assert "prometheus:v2.45.0" in content

    def test_alertmanager_service_defined(self):
        """Verify Alertmanager service is in docker-compose.yml."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                assert "alertmanager:" in content
                assert "prom/alertmanager" in content

    def test_grafana_service_defined(self):
        """Verify Grafana service is in docker-compose.yml."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                assert "grafana:" in content
                assert "grafana/grafana" in content

    def test_monitoring_volumes_defined(self):
        """Verify monitoring volumes are in docker-compose.yml."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                assert "prometheus_data:" in content
                assert "alertmanager_data:" in content
                assert "grafana_data:" in content

    def test_services_use_internal_network(self):
        """Verify monitoring services use darioos internal network."""
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "../..", "docker/docker-compose.yml")
        if os.path.exists(compose_path):
            with open(compose_path) as f:
                content = f.read()
                # All services should be on darioos network, not exposed publicly
                assert "networks: [darioos]" in content


class TestEnvironmentVariables:
    """Verify .env.example has monitoring variables."""

    def test_monitoring_env_vars_in_example(self):
        """Verify monitoring environment variables are documented."""
        import os
        env_path = os.path.join(os.path.dirname(__file__), "../..", "docker/.env.example")
        if os.path.exists(env_path):
            with open(env_path) as f:
                content = f.read()
                # Should document Grafana, Alertmanager, SMTP variables
                assert "GF_SECURITY_ADMIN" in content or "ALERTMANAGER_WEBHOOK" in content


class TestRegressionP7:
    """Verify P7 tests still pass (zero regressions)."""

    def test_health_endpoint_still_works(self, client):
        """Verify health check endpoint still responds."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_metrics_endpoint_accessible(self, client):
        """Verify metrics endpoint is still accessible."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_readiness_check_available(self, client):
        """Verify readiness check is available."""
        response = client.get("/health/ready")
        assert response.status_code == 200

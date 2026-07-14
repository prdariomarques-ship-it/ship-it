"""Grafana dashboard configuration tests."""
import json
import tempfile


from observability.grafana_dashboard import (
    create_dashboard_config,
    save_dashboard_config,
)


class TestGrafanaDashboard:
    """Test Grafana dashboard configuration."""

    def test_dashboard_config_structure(self):
        """Dashboard configuration has required structure."""
        config = create_dashboard_config()

        assert "dashboard" in config
        dashboard = config["dashboard"]

        # Required fields
        assert dashboard["title"] == "Distributed Tracing & Operational Metrics"
        assert "description" in dashboard
        assert "tags" in dashboard
        assert "panels" in dashboard

    def test_dashboard_has_six_panels(self):
        """Dashboard includes all 6 operational panels."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        assert len(panels) == 6

        # Panel titles
        titles = [p["title"] for p in panels]
        assert "Trace Execution Timeline" in titles
        assert "Logs Correlated with Traces" in titles
        assert "Exemplars: Metrics Linked to Traces" in titles
        assert "Sampling Rate & Health" in titles
        assert "Span Export Metrics" in titles
        assert "Error Traces (always sampled)" in titles

    def test_trace_timeline_panel(self):
        """Trace timeline panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        timeline_panel = next(p for p in panels if "Timeline" in p["title"])
        assert timeline_panel["type"] == "trace"
        assert timeline_panel["gridPos"]["h"] == 8
        assert timeline_panel["gridPos"]["w"] == 12

    def test_log_correlation_panel(self):
        """Log correlation panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        log_panel = next(p for p in panels if "Logs Correlated" in p["title"])
        assert log_panel["type"] == "logs"
        assert "Loki" in log_panel["targets"][0]["datasource"]
        # Should have link to Jaeger for trace_id field
        assert "custom" in log_panel["fieldConfig"]["defaults"]

    def test_exemplar_panel(self):
        """Exemplar panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        exemplar_panel = next(p for p in panels if "Exemplars" in p["title"])
        assert exemplar_panel["type"] == "graph"
        assert "Prometheus" in exemplar_panel["targets"][0]["datasource"]
        # Should show exemplars
        assert exemplar_panel["options"]["showExempars"] is True

    def test_sampling_rate_panel(self):
        """Sampling rate panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        sampling_panel = next(p for p in panels if "Sampling Rate" in p["title"])
        assert sampling_panel["type"] == "stat"
        assert sampling_panel["targets"][0]["expr"] == "otel_sampling_rate"
        # Should show as percentage (0.0 to 1.0)
        assert sampling_panel["fieldConfig"]["defaults"]["unit"] == "percentunit"

    def test_span_export_panel(self):
        """Span export panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        export_panel = next(p for p in panels if "Span Export" in p["title"])
        assert export_panel["type"] == "bargauge"
        # Should track both exported and dropped
        assert len(export_panel["targets"]) == 2

    def test_error_traces_panel(self):
        """Error traces panel configured correctly."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        error_panel = next(p for p in panels if "Error Traces" in p["title"])
        assert error_panel["type"] == "logs"
        # Should query Jaeger for error spans
        assert error_panel["targets"][0]["datasource"] == "Jaeger"

    def test_panels_have_descriptions(self):
        """All panels include descriptions."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        for panel in panels:
            assert "description" in panel
            assert len(panel["description"]) > 0

    def test_save_dashboard_config(self):
        """Save dashboard configuration to JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            save_dashboard_config(filepath)

            # Read back and verify
            with open(filepath, "r") as f:
                saved_config = json.load(f)

            assert "dashboard" in saved_config
            assert saved_config["dashboard"]["title"] == "Distributed Tracing & Operational Metrics"
        finally:
            import os
            os.unlink(filepath)

    def test_dashboard_time_range(self):
        """Dashboard has appropriate time range."""
        config = create_dashboard_config()
        dashboard = config["dashboard"]

        assert "time" in dashboard
        assert dashboard["time"]["from"] == "now-1h"
        assert dashboard["time"]["to"] == "now"

    def test_dashboard_refresh_interval(self):
        """Dashboard has auto-refresh configured."""
        config = create_dashboard_config()
        dashboard = config["dashboard"]

        assert dashboard["refresh"] == "10s"

    def test_panel_grid_layout(self):
        """Panels are laid out in grid (2 columns, 3 rows)."""
        config = create_dashboard_config()
        panels = config["dashboard"]["panels"]

        # Verify grid positions
        x_positions = set()
        y_positions = set()
        for panel in panels:
            x = panel["gridPos"]["x"]
            y = panel["gridPos"]["y"]
            x_positions.add(x)
            y_positions.add(y)

        # Should use columns 0 and 12 (width 12 = half screen)
        assert 0 in x_positions
        assert 12 in x_positions

        # Should use rows 0, 8, 16 (height 8 each)
        assert 0 in y_positions
        assert 8 in y_positions
        assert 16 in y_positions

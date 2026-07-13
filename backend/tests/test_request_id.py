"""Request/Correlation ID middleware and its propagation into logs."""
import json
import logging

import pytest

from observability.request_context import REQUEST_ID_HEADER, _request_id, get_request_id
from utils.logging import JsonFormatter, RequestIDFilter, TEXT_FORMAT


@pytest.mark.asyncio
async def test_response_carries_a_generated_request_id_when_client_sends_none(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0


@pytest.mark.asyncio
async def test_response_echoes_back_the_client_supplied_request_id(client):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "client-chosen-id-42"})
    assert response.headers[REQUEST_ID_HEADER] == "client-chosen-id-42"


@pytest.mark.asyncio
async def test_two_requests_get_different_generated_ids(client):
    first = await client.get("/health")
    second = await client.get("/health")
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


def test_get_request_id_is_none_outside_any_request():
    assert get_request_id() is None


def test_get_request_id_reflects_the_contextvar():
    token = _request_id.set("manually-set-id")
    try:
        assert get_request_id() == "manually-set-id"
    finally:
        _request_id.reset(token)


class TestLoggingIntegration:
    def test_json_formatter_omits_request_id_when_absent(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
        RequestIDFilter().filter(record)
        entry = json.loads(JsonFormatter().format(record))
        assert "request_id" not in entry

    def test_json_formatter_includes_request_id_when_set(self):
        token = _request_id.set("json-log-test-id")
        try:
            record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
            RequestIDFilter().filter(record)
            entry = json.loads(JsonFormatter().format(record))
            assert entry["request_id"] == "json-log-test-id"
        finally:
            _request_id.reset(token)

    def test_text_format_includes_a_request_id_placeholder(self):
        assert "%(request_id)s" in TEXT_FORMAT

    def test_text_formatter_renders_dash_when_no_request_id(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
        RequestIDFilter().filter(record)
        rendered = logging.Formatter(TEXT_FORMAT).format(record)
        assert "[-:-]" in rendered

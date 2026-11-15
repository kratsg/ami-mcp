"""Unit tests for structured JSON logging and the request-id middleware."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from ami_mcp.observability import (
    MAX_REQUEST_ID_CHARS,
    JsonFormatter,
    RequestLogMiddleware,
    request_id_var,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from conftest import JsonLog
    from starlette.requests import Request
    from starlette.responses import Response


@pytest.fixture
def client(json_log: JsonLog) -> Iterator[TestClient]:
    """A real Starlette app behind RequestLogMiddleware with a probe that can fail."""
    probe_status = {"code": 200}

    async def healthz(_request: Request) -> Response:
        return PlainTextResponse("probe", status_code=probe_status["code"])

    async def work(_request: Request) -> Response:
        logging.getLogger("ami_mcp.test").info("working")
        return PlainTextResponse("done")

    async def break_probe(_request: Request) -> Response:
        probe_status["code"] = 503
        return PlainTextResponse("broken")

    app = Starlette(
        routes=[
            Route("/healthz", healthz),
            Route("/work", work),
            Route("/break", break_probe),
        ]
    )
    app.add_middleware(RequestLogMiddleware)
    with TestClient(app) as test_client:
        yield test_client


class TestJsonFormatter:
    def test_standard_fields_are_present(self) -> None:
        record = logging.LogRecord(
            "ami_mcp.x", logging.WARNING, "f", 1, "evt", (), None
        )
        entry = json.loads(JsonFormatter().format(record))

        assert entry["logger"] == "ami_mcp.x"
        assert entry["level"] == "warning"
        assert entry["event"] == "evt"
        assert entry["timestamp"].endswith("+00:00")

    def test_request_id_is_added_when_bound(self) -> None:
        reset = request_id_var.set("abc")
        try:
            record = logging.LogRecord("n", logging.INFO, "f", 1, "evt", (), None)
            entry = json.loads(JsonFormatter().format(record))
        finally:
            request_id_var.reset(reset)

        assert entry["request_id"] == "abc"

    def test_extra_fields_are_merged(self) -> None:
        record = logging.LogRecord("n", logging.INFO, "f", 1, "evt", (), None)
        record.fields = {"tool": "ami_execute", "duration_ms": 1.5}  # type: ignore[attr-defined]
        entry = json.loads(JsonFormatter().format(record))

        assert entry["tool"] == "ami_execute"
        assert entry["duration_ms"] == pytest.approx(1.5)


class TestRequestLogMiddleware:
    def test_header_request_id_is_on_every_line(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        client.get("/work", headers={"X-Request-ID": "abc"})

        lines = json_log.lines()
        assert {line["event"] for line in lines} == {"working", "http.request"}
        assert all(line["request_id"] == "abc" for line in lines)

    def test_missing_header_generates_an_id(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        client.get("/work")

        ids = {line["request_id"] for line in json_log.lines()}
        assert len(ids) == 1
        assert ids != {""}

    def test_overlong_id_is_truncated(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        client.get("/work", headers={"X-Request-ID": "x" * 500})

        assert {len(line["request_id"]) for line in json_log.lines()} == {
            MAX_REQUEST_ID_CHARS
        }

    def test_access_line_has_method_path_status_duration(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        client.get("/work", headers={"X-Request-ID": "abc"})

        access = next(
            line for line in json_log.lines() if line["event"] == "http.request"
        )
        assert (access["method"], access["path"], access["status"]) == (
            "GET",
            "/work",
            200,
        )
        assert access["duration_ms"] >= 0

    def test_successful_probe_writes_no_line(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        for _ in range(3):
            assert client.get("/healthz").status_code == 200

        assert json_log.lines() == []

    def test_failing_probe_is_logged(
        self, client: TestClient, json_log: JsonLog
    ) -> None:
        client.get("/break")
        json_log.clear()

        assert client.get("/healthz").status_code == 503

        (line,) = json_log.lines()
        assert (line["event"], line["path"], line["status"]) == (
            "http.request",
            "/healthz",
            503,
        )

    def test_request_id_does_not_leak_to_later_lines(self, client: TestClient) -> None:
        client.get("/work", headers={"X-Request-ID": "abc"})

        assert request_id_var.get() is None

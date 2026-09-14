import unittest

from fastapi import HTTPException

from backend.api.v1.health import _readiness_response


class ReadinessResponseTest(unittest.TestCase):
    def test_healthy_checks_return_ok(self):
        self.assertEqual(
            _readiness_response({"db": "ok", "redis": "ok", "queue": "ok"}),
            {"status": "ok", "checks": {"db": "ok", "redis": "ok", "queue": "ok"}},
        )

    def test_failed_dependency_returns_service_unavailable(self):
        with self.assertRaises(HTTPException) as context:
            _readiness_response({"db": "error", "redis": "ok", "queue": "ok"})

        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(
            context.exception.detail,
            {
                "status": "degraded",
                "checks": {"db": "error", "redis": "ok", "queue": "ok"},
            },
        )

    def test_unprobed_external_queue_does_not_report_a_false_failure(self):
        self.assertEqual(
            _readiness_response({"db": "ok", "redis": "ok", "queue": "unknown"})["status"],
            "ok",
        )

    def test_required_unknown_dependency_returns_service_unavailable(self):
        with self.assertRaises(HTTPException) as context:
            _readiness_response(
                {"db": "ok", "redis": "ok", "queue": "unknown"},
                required_checks={"db", "redis", "queue"},
            )

        self.assertEqual(context.exception.status_code, 503)

    def test_readiness_includes_worker_operational_metrics(self):
        response = _readiness_response(
            {"db": "ok", "redis": "ok", "queue": "ok"},
            details={
                "queue_metrics": {
                    "queue_depth": 4,
                    "oldest_job_age_seconds": 12.5,
                    "retry_count": 2,
                    "failed_job_count": 1,
                    "last_successful_heartbeat_at": "2026-07-12T00:00:00+00:00",
                }
            },
        )
        self.assertEqual(response["details"]["queue_metrics"]["queue_depth"], 4)

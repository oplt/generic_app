import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.observability.schemas import ObservabilityStatusItem
from backend.observability.service import ObservabilityService, build_public_url


def make_settings(**overrides):
    defaults = {
        "GRAFANA_PUBLIC_URL": "http://localhost:3001/",
        "PROMETHEUS_PUBLIC_URL": "http://localhost:9090/",
        "TEMPO_PUBLIC_URL": "http://localhost:3200",
        "GRAFANA_APP_OVERVIEW_DASHBOARD_PATH": "/d/app-overview/application-overview",
        "GRAFANA_API_DASHBOARD_PATH": "/d/api-observability/backend-api",
        "GRAFANA_FRONTEND_DASHBOARD_PATH": "",
        "GRAFANA_DATABASE_DASHBOARD_PATH": "/d/database/database",
        "GRAFANA_CACHE_DASHBOARD_PATH": "/d/cache/cache-redis",
        "GRAFANA_WORKERS_DASHBOARD_PATH": "/d/workers/background-workers",
        "GRAFANA_SCHEDULED_TASKS_DASHBOARD_PATH": "/d/scheduled-tasks/scheduled-tasks",
        "GRAFANA_ERRORS_DASHBOARD_PATH": "/d/errors/error-investigation",
        "GRAFANA_TEMPO_EXPLORE_PATH": "/explore",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ObservabilityServiceTest(unittest.TestCase):
    def test_url_joining_trims_duplicate_slashes(self):
        url = build_public_url("http://localhost:3001/", "/d/api-observability/backend-api")

        self.assertEqual(url, "http://localhost:3001/d/api-observability/backend-api")

    def test_links_return_configured_urls_for_admin(self):
        user = SimpleNamespace(is_admin=True)
        links = ObservabilityService(make_settings()).get_links(user)

        self.assertEqual(
            links.dashboards.api.url,
            "http://localhost:3001/d/api-observability/backend-api",
        )
        self.assertEqual(links.prometheus_url.url, "http://localhost:9090/graph")
        self.assertTrue(links.tempo_explore_url.allowed)

    def test_missing_optional_urls_are_not_configured(self):
        user = SimpleNamespace(is_admin=True)
        links = ObservabilityService(
            make_settings(GRAFANA_FRONTEND_DASHBOARD_PATH="")
        ).get_links(user)

        self.assertIsNone(links.dashboards.frontend.url)
        self.assertFalse(links.dashboards.frontend.configured)

    def test_non_admin_does_not_receive_technical_urls(self):
        user = SimpleNamespace(is_admin=False)
        links = ObservabilityService(make_settings()).get_links(user)

        self.assertIsNone(links.prometheus_url.url)
        self.assertFalse(links.prometheus_url.allowed)


class ObservabilityStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_does_not_crash_when_tools_are_unconfigured(self):
        service = ObservabilityService(
            make_settings(
                GRAFANA_PUBLIC_URL="",
                PROMETHEUS_PUBLIC_URL="",
                TEMPO_PUBLIC_URL="",
            )
        )
        unknown = ObservabilityStatusItem(status="unknown", detail="check unavailable")

        with (
            patch.object(service, "_database_status", AsyncMock(return_value=unknown)),
            patch.object(service, "_cache_status", AsyncMock(return_value=unknown)),
        ):
            status = await service.get_status()

        self.assertIn(status.prometheus.status, {"not_configured", "unknown", "down"})
        self.assertIn(status.grafana.status, {"not_configured", "unknown", "down"})
        self.assertIn(status.tempo.status, {"not_configured", "unknown", "down"})


if __name__ == "__main__":
    unittest.main()

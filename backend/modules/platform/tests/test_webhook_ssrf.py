from __future__ import annotations

import asyncio
import ipaddress
import socket
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.modules.platform.webhook_service import WebhookService


class _FakeResponse:
    def __init__(self, status_code: int, chunks: list[bytes]):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._chunks = chunks
        self.chunks_read = 0

    async def aiter_bytes(self):
        for chunk in self._chunks:
            self.chunks_read += 1
            yield chunk


class _FakeStream:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeAsyncClient:
    response = _FakeResponse(200, [b"ok"])
    init_kwargs: dict = {}
    stream_args: tuple = ()
    stream_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def stream(self, *args, **kwargs):
        type(self).stream_args = args
        type(self).stream_kwargs = kwargs
        return _FakeStream(type(self).response)


class WebhookTargetValidationTest(unittest.IsolatedAsyncioTestCase):
    def test_rejects_unsafe_literal_targets_and_non_http_schemes(self):
        targets = (
            "ftp://example.com/hook",
            "http://localhost/hook",
            "http://127.0.0.1/hook",
            "http://10.0.0.1/hook",
            "http://169.254.169.254/latest/meta-data",
            "http://192.0.2.1/hook",
            "http://224.0.0.1/hook",
            "http://[::1]/hook",
            "http://[fc00::1]/hook",
            "https://user:password@example.com/hook",
        )

        for target in targets:
            with self.subTest(target=target), self.assertRaises(HTTPException) as raised:
                WebhookService._validate_webhook_target(target)
            self.assertEqual(raised.exception.status_code, 422)

    async def test_rejects_any_private_address_in_dns_results(self):
        parsed = WebhookService._parse_webhook_target("https://hooks.example.com/test")
        resolver = AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]
        )
        loop = SimpleNamespace(getaddrinfo=resolver)

        with (
            patch.object(asyncio, "get_running_loop", return_value=loop),
            self.assertRaises(HTTPException) as raised,
        ):
            await WebhookService._resolve_public_addresses(parsed)

        self.assertEqual(raised.exception.status_code, 422)


class WebhookPinnedDeliveryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = WebhookService(AsyncMock())
        self.service.ensure_module_enabled = AsyncMock()
        self.service.get_platform_metadata = AsyncMock(
            return_value=SimpleNamespace(app_name="App", core_domain_plural="Items")
        )
        self.webhook = SimpleNamespace(
            id="webhook-1",
            user_id="user-1",
            target_url="https://hooks.example.com:8443/test?token=public",
            secret="secret",
            last_tested_at=None,
            last_response_status=None,
        )
        self.service.repo.get_webhook_for_user = AsyncMock(return_value=self.webhook)
        self.service._resolve_public_addresses = AsyncMock(
            return_value=(ipaddress.ip_address("93.184.216.34"),)
        )
        self.user = SimpleNamespace(id="user-1")

    async def test_public_target_is_pinned_and_response_read_is_bounded(self):
        _FakeAsyncClient.response = _FakeResponse(
            200,
            [b"a" * (64 * 1024), b"must-not-be-read"],
        )

        with patch(
            "backend.modules.platform.webhook_service.httpx.AsyncClient",
            _FakeAsyncClient,
        ):
            result = await self.service.test_webhook_for_user(self.user, "webhook-1")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["response_preview"], "a" * 500)
        self.assertEqual(_FakeAsyncClient.response.chunks_read, 1)
        self.assertEqual(
            _FakeAsyncClient.stream_args[:2],
            ("POST", "https://93.184.216.34:8443/test?token=public"),
        )
        self.assertEqual(
            _FakeAsyncClient.stream_kwargs["headers"]["Host"], "hooks.example.com:8443"
        )
        self.assertEqual(
            _FakeAsyncClient.stream_kwargs["extensions"]["sni_hostname"],
            "hooks.example.com",
        )
        self.assertFalse(_FakeAsyncClient.stream_kwargs["follow_redirects"])
        self.assertFalse(_FakeAsyncClient.init_kwargs["follow_redirects"])
        self.assertFalse(_FakeAsyncClient.init_kwargs["trust_env"])

    async def test_redirect_is_reported_without_following_it(self):
        _FakeAsyncClient.response = _FakeResponse(302, [b"redirect"])

        with patch(
            "backend.modules.platform.webhook_service.httpx.AsyncClient",
            _FakeAsyncClient,
        ):
            result = await self.service.test_webhook_for_user(self.user, "webhook-1")

        self.assertFalse(result["delivered"])
        self.assertEqual(result["status_code"], 302)
        self.assertFalse(_FakeAsyncClient.stream_kwargs["follow_redirects"])

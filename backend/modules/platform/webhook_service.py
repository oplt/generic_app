import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
from datetime import UTC, datetime
from urllib.parse import ParseResult, urlparse, urlunparse

import httpx
from fastapi import HTTPException

from backend.core.pagination import DEFAULT_PAGE_LIMIT
from backend.modules.identity_access.models import User
from backend.modules.platform.config_service import PlatformConfigService
from backend.modules.platform.models import WebhookEndpoint

logger = logging.getLogger(__name__)

_MAX_WEBHOOK_RESPONSE_BYTES = 64 * 1024
_WEBHOOK_RESPONSE_PREVIEW_CHARS = 500


class WebhookService(PlatformConfigService):
    async def list_webhooks_for_user(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[WebhookEndpoint], int]:
        await self.ensure_module_enabled("webhooks")
        return await self.repo.list_webhooks_for_user(user.id, limit=limit, offset=offset)

    async def create_webhook_for_user(
        self,
        user: User,
        *,
        target_url: str,
        description: str | None,
        events: list[str],
    ) -> WebhookEndpoint:
        await self.ensure_module_enabled("webhooks")
        self._validate_webhook_target(target_url)
        webhook = await self.repo.create_webhook(
            user_id=user.id,
            target_url=target_url,
            description=description,
            secret=secrets.token_urlsafe(24),
            is_active=True,
            events_json=events,
        )
        await self.db.commit()
        await self.db.refresh(webhook)
        logger.info("Webhook created user=%s webhook=%s", user.id, webhook.id)
        return webhook

    async def update_webhook_for_user(
        self, user: User, webhook_id: str, payload: dict
    ) -> WebhookEndpoint:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        for field, value in payload.items():
            if field == "events":
                webhook.events_json = value
            elif field == "target_url" and value is not None:
                self._validate_webhook_target(str(value))
                webhook.target_url = str(value)
            elif value is not None:
                setattr(webhook, field, value)

        await self.db.commit()
        await self.db.refresh(webhook)
        logger.info(
            "Webhook updated user=%s webhook=%s fields=%s", user.id, webhook.id, sorted(payload)
        )
        return webhook

    async def delete_webhook_for_user(self, user: User, webhook_id: str) -> None:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        await self.repo.delete_webhook(webhook)
        await self.db.commit()
        logger.info("Webhook deleted user=%s webhook=%s", user.id, webhook_id)

    async def test_webhook_for_user(self, user: User, webhook_id: str) -> dict:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        metadata = await self.get_platform_metadata()
        payload = {
            "event": "platform.test",
            "sent_at": datetime.now(UTC).isoformat(),
            "app_name": metadata.app_name,
            "core_domain_plural": metadata.core_domain_plural,
            "target_user_id": user.id,
        }
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(webhook.secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        parsed = self._parse_webhook_target(webhook.target_url)
        addresses = await self._resolve_public_addresses(parsed)
        pinned_url, host_header = self._pinned_target(parsed, addresses[0])

        try:
            async with (
                httpx.AsyncClient(
                    timeout=10,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    pinned_url,
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "Host": host_header,
                        "X-Generic-App-Event": payload["event"],
                        "X-Generic-App-Signature": signature,
                    },
                    follow_redirects=False,
                    extensions={"sni_hostname": (parsed.hostname or "").rstrip(".")},
                ) as response,
            ):
                response_preview = await self._bounded_response_preview(response)
            webhook.last_tested_at = datetime.now(UTC)
            webhook.last_response_status = response.status_code
            await self.db.commit()
            await self.db.refresh(webhook)
            if not response.is_success:
                logger.warning(
                    "Webhook test delivery failed user=%s webhook=%s status=%s",
                    user.id,
                    webhook.id,
                    response.status_code,
                )
            return {
                "delivered": response.is_success,
                "status_code": response.status_code,
                "response_preview": response_preview,
                "error": None,
            }
        except httpx.HTTPError as exc:
            webhook.last_tested_at = datetime.now(UTC)
            webhook.last_response_status = None
            await self.db.commit()
            await self.db.refresh(webhook)
            logger.warning(
                "Webhook test request failed user=%s webhook=%s error_type=%s",
                user.id,
                webhook.id,
                type(exc).__name__,
            )
            return {
                "delivered": False,
                "status_code": None,
                "response_preview": None,
                "error": str(exc),
            }

    @staticmethod
    def _validate_webhook_target(target_url: str) -> None:
        WebhookService._parse_webhook_target(target_url)

    @staticmethod
    def _parse_webhook_target(target_url: str) -> ParseResult:
        try:
            parsed = urlparse(target_url)
            host = (parsed.hostname or "").strip().lower().rstrip(".")
            port = parsed.port
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Webhook target URL is invalid") from exc
        if parsed.scheme.lower() not in {"http", "https"}:
            raise HTTPException(status_code=422, detail="Webhook target scheme is not allowed")
        if not host:
            raise HTTPException(status_code=422, detail="Webhook target host is required")
        if parsed.username or parsed.password:
            raise HTTPException(
                status_code=422, detail="Webhook target credentials are not allowed"
            )
        if port is not None and port < 1:
            raise HTTPException(status_code=422, detail="Webhook target port is invalid")
        if host in {"localhost", "metadata.google.internal"} or host.endswith(
            (".internal", ".localhost")
        ):
            raise HTTPException(status_code=422, detail="Webhook target host is not allowed")
        if "." not in host and ":" not in host:
            raise HTTPException(status_code=422, detail="Webhook target host is not allowed")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return parsed
        WebhookService._ensure_public_address(ip)
        return parsed

    @staticmethod
    def _ensure_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise HTTPException(status_code=422, detail="Webhook target host is not allowed")

    @staticmethod
    async def _resolve_public_addresses(
        parsed: ParseResult,
    ) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        host = (parsed.hostname or "").rstrip(".")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            WebhookService._ensure_public_address(literal)
            return (literal,)

        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host.encode("idna").decode("ascii"),
                parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (OSError, UnicodeError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Webhook target host could not be resolved",
            ) from exc

        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for info in infos:
            if info[0] not in {socket.AF_INET, socket.AF_INET6}:
                continue
            address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise HTTPException(status_code=422, detail="Webhook target host could not be resolved")
        for address in addresses:
            WebhookService._ensure_public_address(address)
        return tuple(addresses)

    @staticmethod
    def _pinned_target(
        parsed: ParseResult,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> tuple[str, str]:
        hostname = (parsed.hostname or "").rstrip(".")
        address_text = f"[{address}]" if address.version == 6 else str(address)
        pinned_netloc = address_text
        if parsed.port is not None:
            pinned_netloc = f"{pinned_netloc}:{parsed.port}"

        host_header = f"[{hostname}]" if ":" in hostname else hostname
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        if parsed.port is not None and parsed.port != default_port:
            host_header = f"{host_header}:{parsed.port}"
        pinned_url = urlunparse(
            (
                parsed.scheme.lower(),
                pinned_netloc,
                parsed.path or "/",
                parsed.params,
                parsed.query,
                "",
            )
        )
        return pinned_url, host_header

    @staticmethod
    async def _bounded_response_preview(response: httpx.Response) -> str | None:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            remaining = _MAX_WEBHOOK_RESPONSE_BYTES - len(content)
            if remaining <= 0:
                break
            content.extend(chunk[:remaining])
            if len(content) >= _MAX_WEBHOOK_RESPONSE_BYTES:
                break
        if not content:
            return None
        return content.decode("utf-8", errors="replace")[:_WEBHOOK_RESPONSE_PREVIEW_CHARS]

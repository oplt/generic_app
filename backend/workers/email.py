"""Email delivery helpers for in-process and Celery-backed execution."""

import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.core.config import settings
from backend.observability.workflow import observe_async_workflow

logger = logging.getLogger(__name__)


@observe_async_workflow("email", "send")
async def send_email(
    *, to: str, subject: str, html_body: str, text_body: str | None = None
) -> None:
    if not settings.SMTP_HOST:
        logger.info(
            "email_delivery_skipped",
            extra={"event_name": "email_delivery_skipped", "reason": "smtp_not_configured"},
        )
        return

    try:
        import aiosmtplib  # optional dep

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_TLS,
        )
        logger.info("email_delivery_sent", extra={"event_name": "email_delivery_sent"})
    except ImportError:
        logger.exception(
            "email_delivery_failed",
            extra={"event_name": "email_delivery_failed", "error_type": "ImportError"},
        )
        raise
    except Exception as exc:
        logger.exception(
            "email_delivery_failed",
            extra={
                "event_name": "email_delivery_failed",
                "error_type": type(exc).__name__,
            },
        )
        raise


def send_email_sync(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    from backend.workers.async_dispatch import run_async_in_sync_context

    run_async_in_sync_context(
        send_email(
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    )


def queue_email(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    payload = {
        "to": to,
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }

    if settings.is_production and settings.CELERY_TASK_ALWAYS_EAGER:
        raise RuntimeError(
            "CELERY_TASK_ALWAYS_EAGER is forbidden in production; run a Celery worker"
        )

    # Useful for tests or extremely lightweight local runs without a worker process.
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            send_email_sync(**payload)
        else:
            loop.create_task(send_email(**payload))
        return

    from backend.workers.tasks import send_email_task

    send_email_task.apply_async(kwargs=payload, queue=settings.CELERY_EMAIL_QUEUE)


async def send_verification_email(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    await send_email(
        to=to,
        subject="Verify your email address",
        html_body=f"""
        <p>Thanks for signing up. Click the link below to verify your email:</p>
        <p><a href="{link}">{link}</a></p>
        <p>This link expires in 24 hours.</p>
        """,
        text_body=(
            f"Thanks for signing up.\nVerify your email: {link}\nThis link expires in 24 hours."
        ),
    )


async def send_password_reset_email(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    await send_email(
        to=to,
        subject="Reset your password",
        html_body=f"""
        <p>We received a request to reset your password. Click the link below:</p>
        <p><a href="{link}">{link}</a></p>
        <p>This link expires in 1 hour. If you did not request this, ignore this email.</p>
        """,
        text_body=(
            "We received a request to reset your password.\n"
            f"Reset link: {link}\n"
            "This link expires in 1 hour. If you did not request this, ignore this email."
        ),
    )

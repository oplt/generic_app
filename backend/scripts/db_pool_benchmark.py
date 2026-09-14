"""Measure bounded SQLAlchemy/PostgreSQL pool behavior with a lightweight query."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.config import settings
from backend.db import session as db_session


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


async def _one_request(hold_seconds: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with db_session.SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            if hold_seconds:
                await asyncio.sleep(hold_seconds)
        return {"ok": True, "latency_ms": (time.perf_counter() - started) * 1000}
    except Exception as exc:  # pragma: no cover - exercised against a live PostgreSQL instance
        return {
            "ok": False,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "error": type(exc).__name__,
        }


async def _run_burst(concurrency: int, hold_seconds: float) -> list[dict[str, Any]]:
    return await asyncio.gather(
        *(_one_request(hold_seconds) for _ in range(concurrency))
    )


async def _run_sustained(
    concurrency: int,
    duration_seconds: float,
    hold_seconds: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    deadline = time.perf_counter() + duration_seconds
    lock = asyncio.Lock()

    async def worker() -> None:
        while time.perf_counter() < deadline:
            result = await _one_request(hold_seconds)
            async with lock:
                results.append(result)

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return results


def _build_report(
    results: list[dict[str, Any]],
    *,
    concurrency: int,
    duration_seconds: float,
    hold_seconds: float,
    mode: str,
) -> dict[str, Any]:
    latencies = [float(result["latency_ms"]) for result in results]
    errors = Counter(str(result["error"]) for result in results if not result["ok"])
    return {
        "mode": mode,
        "configuration": {
            "concurrency": concurrency,
            "duration_seconds": duration_seconds,
            "hold_seconds": hold_seconds,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_capacity": settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW,
            "pool_timeout_seconds": settings.DB_POOL_TIMEOUT_SECONDS,
        },
        "results": {
            "requests": len(results),
            "successes": sum(1 for result in results if result["ok"]),
            "errors": sum(1 for result in results if not result["ok"]),
            "error_types": dict(errors),
            "latency_ms": {
                "p50": _percentile(latencies, 50),
                "p95": _percentile(latencies, 95),
                "p99": _percentile(latencies, 99),
                "max": max(latencies) if latencies else None,
            },
        },
    }


def _print_human(report: dict[str, Any]) -> None:
    configuration = report["configuration"]
    results = report["results"]
    latency = results["latency_ms"]
    print(
        f"{report['mode']} PostgreSQL pool benchmark: "
        f"{results['successes']}/{results['requests']} successful"
    )
    print(
        "capacity="
        f"{configuration['pool_capacity']} "
        f"(base={configuration['pool_size']}, overflow={configuration['max_overflow']}), "
        f"pool_timeout={configuration['pool_timeout_seconds']}s"
    )
    print(
        f"latency_ms p50={latency['p50']} p95={latency['p95']} "
        f"p99={latency['p99']} max={latency['max']}"
    )
    if results["error_types"]:
        print(f"errors={results['error_types']}")


async def _benchmark(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "burst":
        results = await _run_burst(args.concurrency, args.hold_seconds)
    else:
        results = await _run_sustained(
            args.concurrency,
            args.duration_seconds,
            args.hold_seconds,
        )
    return _build_report(
        results,
        concurrency=args.concurrency,
        duration_seconds=args.duration_seconds,
        hold_seconds=args.hold_seconds,
        mode=args.mode,
    )


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return await _benchmark(args)
    finally:
        await db_session.engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("burst", "sustained"), default="sustained")
    parser.add_argument("--concurrency", type=_concurrency, default=10)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.0,
        help="Keep each transaction open after SELECT 1 to exercise pool contention.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write the complete report as JSON while retaining the human-readable stdout.",
    )
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.hold_seconds < 0:
        parser.error("duration-seconds must be positive and hold-seconds must not be negative")
    if args.mode == "burst":
        args.duration_seconds = 0.0
    return args


def _concurrency(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("concurrency must be an integer") from exc
    if not 1 <= parsed <= 1000:
        raise argparse.ArgumentTypeError("concurrency must be between 1 and 1000")
    return parsed


def main() -> int:
    args = _parse_args()
    report = asyncio.run(_run_cli(args))
    _print_human(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["results"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

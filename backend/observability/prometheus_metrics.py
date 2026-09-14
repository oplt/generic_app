"""Prometheus metric definitions for the FastAPI backend."""

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
)

http_exceptions_total = Counter(
    "http_exceptions_total",
    "Total unhandled HTTP exceptions",
    ["method", "route", "exception_type"],
)

startup_dependency_duration_seconds = Histogram(
    "startup_dependency_duration_seconds",
    "Time spent initializing startup dependencies",
)

workflow_events_total = Counter(
    "workflow_events_total",
    "Completed and failed application workflow operations",
    ["workflow", "operation", "outcome"],
)

workflow_duration_seconds = Histogram(
    "workflow_duration_seconds",
    "Application workflow duration",
    ["workflow", "operation"],
)

worker_jobs_total = Counter(
    "worker_jobs_total",
    "Background jobs by type and outcome",
    ["job_type", "outcome"],
)

worker_job_duration_seconds = Histogram(
    "worker_job_duration_seconds",
    "Background job duration",
    ["job_type"],
)

worker_job_retries_total = Counter(
    "worker_job_retries_total",
    "Background job retries observed",
    ["job_type"],
)

worker_job_queue_latency_seconds = Histogram(
    "worker_job_queue_latency_seconds",
    "Seconds from job availability to worker start",
    ["job_type"],
)

worker_queue_depth = Gauge(
    "worker_queue_depth",
    "Current Redis queue depth",
    ["queue"],
)

worker_oldest_job_age_seconds = Gauge(
    "worker_oldest_job_age_seconds",
    "Age of the oldest queued or running application job",
)

worker_retry_count = Gauge(
    "worker_retry_count",
    "Current application job retry count",
)

worker_failed_job_count = Gauge(
    "worker_failed_job_count",
    "Current failed application job count",
)

worker_heartbeat_timestamp_seconds = Gauge(
    "worker_heartbeat_timestamp_seconds",
    "Unix timestamp of the last successful worker heartbeat check",
    ["worker"],
)

worker_beat_schedule_lock_total = Counter(
    "worker_beat_schedule_lock_total",
    "Celery beat schedule singleton lock attempts",
    ["schedule", "backend", "outcome"],
)

db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Checked-out PostgreSQL connections",
    ["pool"],
)

db_pool_size = Gauge(
    "db_pool_size",
    "Configured PostgreSQL pool size",
    ["pool"],
)

db_pool_overflow = Gauge(
    "db_pool_overflow",
    "PostgreSQL connections above the base pool size",
    ["pool"],
)

db_pool_checkout_total = Counter(
    "db_pool_checkout_total",
    "Successful PostgreSQL pool checkouts",
    ["pool"],
)

db_pool_checkout_errors_total = Counter(
    "db_pool_checkout_errors_total",
    "PostgreSQL pool checkout or acquisition errors",
    ["pool"],
)

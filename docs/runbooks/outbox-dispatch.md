# Outbox dispatch lease and duplicate-safety

`background_job_outbox` uses a short database claim transaction followed by a broker call and a
separate compare-and-set acknowledgement:

1. The dispatcher selects pending or expired `dispatching` rows with `FOR UPDATE SKIP LOCKED`,
   assigns a `lease_token`, increments `attempts`, and commits.
2. Celery publishing happens after that commit, so broker latency does not hold row locks.
3. The dispatcher acknowledges success or schedules retry with an update guarded by the row ID,
   `status='dispatching'`, and the same `lease_token`.

If the process dies after claim, after broker acceptance, or before acknowledgement, the lease
becomes eligible after `OUTBOX_DISPATCH_LEASE_SECONDS` (default 600 seconds). A stale dispatcher
cannot acknowledge a claim that another dispatcher has already reclaimed because its token no
longer matches.

The `job_id` is the stable operation key. The outbox payload passes it unchanged to
`index_rag_document_task`; the ingestion consumer locks that job row, treats completed work as a
no-op, and defers an actively heartbeating duplicate until the lease window. A duplicate Celery
delivery therefore does not create a second logical ingestion attempt, while a worker crash after
the first heartbeat remains retryable instead of being acknowledged as a false success.
At-least-once delivery remains intentional: if a provider accepts a message and the process dies
before the acknowledgement, the message can be published again, but the consumer's operation key
bounds the externally visible effect.

To exercise the boundaries in an isolated PostgreSQL/Redis/Celery environment, pause or terminate
the dispatcher at each of these points and run the scheduled dispatcher again after the lease:

- after the claim commit and before `apply_async`;
- after `apply_async` returns and before the acknowledgement commit;
- during acknowledgement commit.

Verify that the row is eventually `dispatched` or retryable, no row lock remains held during the
broker delay, and the ingestion job has one completed logical operation. The focused unit tests
cover claim/publish/ack ordering, broker failure release, stale-token compare-and-set behavior,
and duplicate active-consumer suppression.

# Tenant integrity migration

Migration `b4e2d8a61f03` stops before changing the schema when existing RAG or chat
rows contain orphaned tenant references or disagree with their parent document.
Run the checks below against a database snapshot before deployment.

## Preflight

Check each scoped table for missing referenced rows:

```sql
SELECT 'rag_documents.organization_id', count(*)
FROM rag_documents r LEFT JOIN organizations o ON o.id = r.organization_id
WHERE r.organization_id IS NOT NULL AND o.id IS NULL
UNION ALL
SELECT 'rag_documents.project_id', count(*)
FROM rag_documents r LEFT JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL AND p.id IS NULL
UNION ALL
SELECT 'rag_chunks.organization_id', count(*)
FROM rag_chunks r LEFT JOIN organizations o ON o.id = r.organization_id
WHERE r.organization_id IS NOT NULL AND o.id IS NULL
UNION ALL
SELECT 'rag_chunks.project_id', count(*)
FROM rag_chunks r LEFT JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL AND p.id IS NULL
UNION ALL
SELECT 'rag_queries.organization_id', count(*)
FROM rag_queries r LEFT JOIN organizations o ON o.id = r.organization_id
WHERE r.organization_id IS NOT NULL AND o.id IS NULL
UNION ALL
SELECT 'rag_queries.project_id', count(*)
FROM rag_queries r LEFT JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL AND p.id IS NULL
UNION ALL
SELECT 'rag_ingestion_jobs.project_id', count(*)
FROM rag_ingestion_jobs r LEFT JOIN projects p ON p.id = r.project_id
WHERE r.project_id IS NOT NULL AND p.id IS NULL
UNION ALL
SELECT 'chat_conversations.organization_id', count(*)
FROM chat_conversations r LEFT JOIN organizations o ON o.id = r.organization_id
WHERE r.organization_id IS NOT NULL AND o.id IS NULL;
```

Check document/child scope consistency:

```sql
SELECT c.id AS chunk_id, d.id AS document_id
FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
WHERE c.user_id IS DISTINCT FROM d.user_id
   OR c.organization_id IS DISTINCT FROM d.organization_id
   OR c.project_id IS DISTINCT FROM d.project_id;

SELECT j.id AS job_id, d.id AS document_id
FROM rag_ingestion_jobs j JOIN rag_documents d ON d.id = j.document_id
WHERE j.user_id IS DISTINCT FROM d.user_id
   OR j.project_id IS DISTINCT FROM d.project_id;
```

## Repair

Review each result against the owning user before changing it. Orphaned optional
project references may be set to `NULL`. Replace an orphaned organization with a
verified organization or set it to `NULL` only when the row is intentionally
personal. For chunks and ingestion jobs, copy the authoritative scope from their
parent document. Take a backup and rerun every preflight query before upgrading.

## Project organization tenancy

Migration `d3e8f1a2b509` adds `projects.organization_id` (NOT NULL), backfills it from the
owner's earliest membership (creating a personal organization when missing), aligns
existing RAG/chat rows that already reference a project, and installs deferred triggers so
`organization_id` must match `projects.organization_id` whenever `project_id` is set.

See [ADR 0004](../adr/0004-tenant-organization-source-of-truth.md).

Preflight after backfill:

```sql
SELECT count(*) FROM projects WHERE organization_id IS NULL;

SELECT 'rag_documents', count(*)
FROM rag_documents d
JOIN projects p ON p.id = d.project_id
WHERE d.organization_id IS DISTINCT FROM p.organization_id
UNION ALL
SELECT 'rag_chunks', count(*)
FROM rag_chunks c
JOIN projects p ON p.id = c.project_id
WHERE c.organization_id IS DISTINCT FROM p.organization_id
UNION ALL
SELECT 'rag_queries', count(*)
FROM rag_queries q
JOIN projects p ON p.id = q.project_id
WHERE q.organization_id IS DISTINCT FROM p.organization_id
UNION ALL
SELECT 'chat_conversations', count(*)
FROM chat_conversations c
JOIN projects p ON p.id = c.project_id
WHERE c.organization_id IS DISTINCT FROM p.organization_id;
```

## Delete behavior

| Deleted row | Result |
| --- | --- |
| Project | Optional `project_id` is set to `NULL` on RAG documents, chunks, queries, ingestion jobs, and chat conversations. |
| Organization | Delete is rejected while a project, RAG, or chat row references it. Reassign or clear those rows first. |
| RAG document | Its chunks and ingestion jobs are deleted by the existing cascade. |

# RAG document deduplication migration

Active document fingerprints are unique within the tuple
`(user_id, organization_id, project_id, content_fingerprint)`. A missing
organization or project is treated as one explicit personal scope, and deleted
documents are excluded so a replacement upload remains possible.

The migration stops before creating the index if active duplicate tuples already
exist. Identify them with:

```sql
SELECT user_id, organization_id, project_id, content_fingerprint, array_agg(id) AS document_ids
FROM rag_documents
WHERE deleted_at IS NULL AND content_fingerprint IS NOT NULL
GROUP BY user_id, organization_id, project_id, content_fingerprint
HAVING count(*) > 1;
```

Review duplicate rows with their owners. Keep one document/job, mark superseded
rows deleted or remove them through the normal document cleanup path, and verify
that referenced storage objects and outbox events are handled before retrying the
migration. Do not clear fingerprints merely to bypass the preflight; that would
remove the invariant for those documents.

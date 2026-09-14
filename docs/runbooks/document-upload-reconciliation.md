# Document upload reconciliation

An upload gets its object key before the storage write. If any database step fails
before commit, the service rolls the session back and deletes that key. The key is
derived from the generated document-attempt ID, so cleanup cannot target an object
created by another attempt.

`rag_document_upload_compensation_total{outcome="deleted"}` counts successful
cleanup. `outcome="delete_failed"` means the database transaction was rolled back
but the object-storage delete needs operational attention.

For crash recovery, periodically compare private objects under `rag/` with
`rag_documents.storage_path` and remove objects older than the upload retention
window that have no committed document row. Keep object-storage lifecycle expiry
enabled as a second safety net; never delete a key referenced by a non-deleted
document row.

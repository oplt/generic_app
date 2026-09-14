# API ↔ frontend contract coverage

Generated: 2026-09-14T21:10:32.844Z

## Summary

| Class | Count |
| --- | ---: |
| UI-used | 117 |
| Programmatic / API-only | 7 |
| Health / observability | 7 |
| Internal | 5 |
| Currently orphaned | 29 |
| OpenAPI operations | 165 |

## Contract violations (CI-failing)

_None._

## Handwritten API modules

| File | Class |
| --- | --- |
| `api/admin.ts` | B_generated_wrapper |
| `api/ai.ts` | C_duplicate_handwritten |
| `api/auth.ts` | C_duplicate_handwritten |
| `api/axiosClient.ts` | A_transport |
| `api/calendar.ts` | C_duplicate_handwritten |
| `api/client.ts` | A_transport |
| `api/developerDiagnostics.ts` | C_duplicate_handwritten |
| `api/developerDiagnosticsEvents.ts` | A_transport |
| `api/diagnostics.ts` | B_generated_wrapper |
| `api/jobs.ts` | B_generated_wrapper |
| `api/memory.ts` | B_generated_wrapper |
| `api/notifications.ts` | C_duplicate_handwritten |
| `api/orvalMutator.ts` | A_transport |
| `api/platform.ts` | C_duplicate_handwritten |
| `api/policy.ts` | B_generated_wrapper |
| `api/profile.ts` | B_generated_wrapper |
| `api/projects.ts` | C_duplicate_handwritten |
| `api/ragEvaluation.ts` | B_generated_wrapper |
| `api/ragIndexes.ts` | B_generated_wrapper |
| `api/settings.ts` | C_duplicate_handwritten |
| `api/users.ts` | C_duplicate_handwritten |

## Currently orphaned (informational)

Present in OpenAPI + SDK but no non-generated frontend caller. Not a CI failure.

- `GET /api/v1/admin/audit-logs` → `listAuditLogsApiV1AdminAuditLogsGet`
- `GET /api/v1/admin/metrics` → `getMetricsApiV1AdminMetricsGet`
- `GET /api/v1/admin/users/{user_id}` → `getUserApiV1AdminUsersUserIdGet`
- `PATCH /api/v1/ai/evaluation-datasets/{dataset_id}` → `updateDatasetApiV1AiEvaluationDatasetsDatasetIdPatch`
- `GET /api/v1/ai/providers` → `listProvidersApiV1AiProvidersGet`
- `POST /api/v1/ai/runs/async` → `queueRunApiV1AiRunsAsyncPost`
- `GET /api/v1/chat/conversations` → `listConversationsApiV1ChatConversationsGet`
- `POST /api/v1/chat/conversations` → `createConversationApiV1ChatConversationsPost`
- `DELETE /api/v1/chat/conversations/{conversation_id}` → `deleteConversationApiV1ChatConversationsConversationIdDelete`
- `GET /api/v1/chat/conversations/{conversation_id}` → `getConversationApiV1ChatConversationsConversationIdGet`
- `PATCH /api/v1/chat/conversations/{conversation_id}` → `updateConversationApiV1ChatConversationsConversationIdPatch`
- `POST /api/v1/chat/conversations/{conversation_id}/clear` → `clearConversationApiV1ChatConversationsConversationIdClearPost`
- `POST /api/v1/chat/conversations/{conversation_id}/messages` → `sendMessageApiV1ChatConversationsConversationIdMessagesPost`
- `POST /api/v1/chat/conversations/{conversation_id}/messages/stream` → `streamMessageApiV1ChatConversationsConversationIdMessagesStreamPost`
- `GET /api/v1/rag/admin/evaluation/runs/{run_id}/export` → `exportRunApiV1RagAdminEvaluationRunsRunIdExportGet`
- `GET /api/v1/rag/admin/index-versions` → `listIndexVersionsApiV1RagAdminIndexVersionsGet`
- `POST /api/v1/rag/ask` → `askRagApiV1RagAskPost`
- `GET /api/v1/rag/documents` → `listDocumentsApiV1RagDocumentsGet`
- `POST /api/v1/rag/documents/upload` → `uploadDocumentApiV1RagDocumentsUploadPost`
- `DELETE /api/v1/rag/documents/{document_id}` → `deleteDocumentApiV1RagDocumentsDocumentIdDelete`
- `GET /api/v1/rag/documents/{document_id}` → `getDocumentApiV1RagDocumentsDocumentIdGet`
- `GET /api/v1/rag/documents/{document_id}/chunks` → `listDocumentChunksApiV1RagDocumentsDocumentIdChunksGet`
- `POST /api/v1/rag/documents/{document_id}/index` → `indexDocumentApiV1RagDocumentsDocumentIdIndexPost`
- `POST /api/v1/rag/documents/{document_id}/reindex` → `reindexDocumentApiV1RagDocumentsDocumentIdReindexPost`
- `GET /api/v1/rag/jobs` → `listJobsApiV1RagJobsGet`
- `GET /api/v1/rag/jobs/{job_id}` → `getJobApiV1RagJobsJobIdGet`
- `POST /api/v1/rag/jobs/{job_id}/retry` → `retryJobApiV1RagJobsJobIdRetryPost`
- `GET /api/v1/rag/queries` → `listQueriesApiV1RagQueriesGet`
- `POST /api/v1/rag/retrieve` → `retrieveChunksApiV1RagRetrievePost`

## How to refresh

```bash
cd frontend && npm run api:contract
```

Intentional API-only allow-list: `frontend/openapi/intentional-api-only.json`.

See also: [frontend-api-contract.md](frontend-api-contract.md).

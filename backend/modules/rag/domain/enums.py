from enum import StrEnum


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(StrEnum):
    UPLOAD = "upload"
    API = "api"
    MANUAL = "manual"

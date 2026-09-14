const MAX_DOCUMENT_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_DOCUMENT_EXTENSIONS = new Set([".txt", ".md", ".json", ".ndjson"]);

export function validateDocumentUpload(file: File): string | null {
    if (file.size > MAX_DOCUMENT_UPLOAD_BYTES) {
        return "Document uploads must be 10 MB or smaller.";
    }
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ALLOWED_DOCUMENT_EXTENSIONS.has(extension)) {
        return "Choose a .txt, .md, .json, or .ndjson file.";
    }
    return null;
}

const MAX_CHAT_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_CHAT_EXTENSIONS = new Set([".pdf", ".txt", ".md", ".docx", ".csv"]);

export function validateChatUpload(file: File): string | null {
    if (file.size > MAX_CHAT_UPLOAD_BYTES) {
        return "Document uploads must be 10 MB or smaller.";
    }
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ALLOWED_CHAT_EXTENSIONS.has(extension)) {
        return "Choose a .pdf, .txt, .md, .docx, or .csv file.";
    }
    return null;
}

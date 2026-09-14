import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { uploadRagDocument } from "../api";
import { validateChatUpload } from "../uploadValidation";
import type { RagUploadResponse } from "../types";
import type { UploadProgressState } from "../components/DocumentUpload";

export function useDocumentUpload(projectId?: string | null, onSuccess?: () => Promise<unknown> | unknown) {
    const [progress, setProgress] = useState<UploadProgressState | null>(null);
    const [validationError, setValidationError] = useState<string | null>(null);
    const mutation = useMutation({
        mutationFn: (file: File) => uploadRagDocument(file, projectId, (value) => {
            setProgress((current) => current ? { ...current, percent: value.percent } : current);
        }),
        onSuccess: (result, file) => {
            setProgress({
                filename: file.name,
                percent: 100,
                job: result.ingestion_job,
                duplicate: result.duplicate,
            });
            setValidationError(null);
            void onSuccess?.();
        },
    });

    function upload(file: File) {
        const error = validateChatUpload(file);
        if (error) {
            setValidationError(error);
            return false;
        }
        setValidationError(null);
        setProgress({ filename: file.name, percent: 0, job: null });
        mutation.mutate(file);
        return true;
    }

    return {
        upload,
        progress,
        error: validationError ?? mutation.error,
        isUploading: mutation.isPending,
        reset: () => {
            mutation.reset();
            setProgress(null);
            setValidationError(null);
        },
        response: mutation.data as RagUploadResponse | undefined,
    };
}

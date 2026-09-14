import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
    activateRagIndexVersion,
    createRagIndexVersion,
    getRagIndexStatus,
    reindexStaleRagDocuments,
    rollbackRagIndexVersion,
    validateRagIndexVersion,
} from "../../../api/ragIndexes";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

export type VersionAction = "activate" | "rollback" | "validate";

export function useRagIndexes() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const [pendingAction, setPendingAction] = useState<{
        type: VersionAction;
        versionId: string;
        versionKey: string;
    } | null>(null);

    const statusQuery = useQuery({
        queryKey: queryKeys.admin.ragIndexStatus,
        queryFn: getRagIndexStatus,
    });

    const refresh = () => void client.invalidateQueries({ queryKey: queryKeys.admin.ragIndexStatus });

    const createMutation = useMutation({
        mutationFn: () => createRagIndexVersion("Created from admin UI"),
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to create index version."),
    });
    const validateMutation = useMutation({
        mutationFn: validateRagIndexVersion,
        onSuccess: () => {
            setPendingAction(null);
            refresh();
        },
        onError: (error) => toastError(error, "Failed to validate index version."),
    });
    const activateMutation = useMutation({
        mutationFn: activateRagIndexVersion,
        onSuccess: () => {
            setPendingAction(null);
            refresh();
        },
        onError: (error) => toastError(error, "Failed to activate index version."),
    });
    const rollbackMutation = useMutation({
        mutationFn: rollbackRagIndexVersion,
        onSuccess: () => {
            setPendingAction(null);
            refresh();
        },
        onError: (error) => toastError(error, "Failed to roll back index version."),
    });
    const reindexMutation = useMutation({
        mutationFn: () => reindexStaleRagDocuments(50),
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to enqueue stale reindex jobs."),
    });

    function requestAction(type: VersionAction, versionId: string, versionKey: string) {
        setPendingAction({ type, versionId, versionKey });
    }

    function confirmPendingAction() {
        if (!pendingAction) return;
        if (pendingAction.type === "validate") {
            validateMutation.mutate(pendingAction.versionId);
        } else if (pendingAction.type === "activate") {
            activateMutation.mutate(pendingAction.versionId);
        } else {
            rollbackMutation.mutate(pendingAction.versionId);
        }
    }

    const actionPending =
        validateMutation.isPending || activateMutation.isPending || rollbackMutation.isPending;

    return {
        statusQuery,
        pendingAction,
        setPendingAction,
        createMutation,
        validateMutation,
        activateMutation,
        rollbackMutation,
        reindexMutation,
        requestAction,
        confirmPendingAction,
        actionPending,
    };
}

export type RagIndexesModel = ReturnType<typeof useRagIndexes>;

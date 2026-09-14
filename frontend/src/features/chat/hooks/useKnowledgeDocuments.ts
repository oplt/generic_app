import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    deleteRagDocument,
    getRagIngestionJob,
    listRagDocuments,
    listRagIngestionJobs,
    reindexRagDocument,
    retryRagIngestionJob,
} from "../api";
import { queryKeys } from "../../../config/queryKeys";

export function useKnowledgeDocuments(projectId?: string | null) {
    const queryClient = useQueryClient();
    const documentsKey = queryKeys.chat.documentsForProject(projectId);
    const jobsKey = queryKeys.chat.ingestionJobsForProject(projectId);
    const documentsQuery = useQuery({
        queryKey: documentsKey,
        queryFn: () => listRagDocuments(projectId),
    });
    const jobsQuery = useQuery({
        queryKey: jobsKey,
        queryFn: listRagIngestionJobs,
        refetchInterval: (query) => {
            const jobs = query.state.data ?? [];
            return jobs.some((job) => job.status === "pending" || job.status === "running")
                ? 3_000
                : false;
        },
    });
    const invalidate = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: queryKeys.chat.documents }),
            queryClient.invalidateQueries({ queryKey: queryKeys.chat.ingestionJobs }),
        ]);
    };
    const retryMutation = useMutation({
        mutationFn: retryRagIngestionJob,
        onSuccess: invalidate,
    });
    const reindexMutation = useMutation({
        mutationFn: reindexRagDocument,
        onSuccess: invalidate,
    });
    const deleteMutation = useMutation({
        mutationFn: deleteRagDocument,
        onSuccess: invalidate,
    });

    return {
        documents: documentsQuery.data ?? [],
        jobs: jobsQuery.data ?? [],
        isLoading: documentsQuery.isLoading || jobsQuery.isLoading,
        error: documentsQuery.error ?? jobsQuery.error,
        mutationError: retryMutation.error ?? reindexMutation.error ?? deleteMutation.error,
        refetch: documentsQuery.refetch,
        getJob: getRagIngestionJob,
        retry: retryMutation.mutate,
        retryAsync: retryMutation.mutateAsync,
        retryPending: retryMutation.isPending,
        reindex: reindexMutation.mutate,
        reindexPending: reindexMutation.isPending,
        remove: deleteMutation.mutate,
        removePending: deleteMutation.isPending,
        invalidate,
    };
}

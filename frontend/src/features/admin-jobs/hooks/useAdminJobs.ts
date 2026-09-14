import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    cancelConsoleJob,
    getConsoleJob,
    listConsoleJobs,
    retryConsoleJob,
    type ConsoleJob,
} from "../../../api/jobs";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

export function useAdminJobs() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const [status, setStatus] = useState("");
    const [jobType, setJobType] = useState("");
    const [queue, setQueue] = useState("");
    const [projectId, setProjectId] = useState("");
    const [failedOnly, setFailedOnly] = useState(false);
    const [selected, setSelected] = useState<ConsoleJob | null>(null);
    const [cancelTarget, setCancelTarget] = useState<ConsoleJob | null>(null);

    const filters = { status, jobType, queue, projectId, failedOnly };

    const listQuery = useQuery({
        queryKey: queryKeys.admin.jobs(filters),
        queryFn: () =>
            listConsoleJobs({
                status: status || undefined,
                job_type: jobType || undefined,
                queue: queue || undefined,
                project_id: projectId || undefined,
                failed_only: failedOnly || undefined,
                limit: 100,
            }),
    });

    const refresh = () => void client.invalidateQueries({ queryKey: ["admin", "jobs"] });

    const detailMutation = useMutation({
        mutationFn: (job: ConsoleJob) => getConsoleJob(job.id, job.source),
        onSuccess: setSelected,
        onError: (error) => toastError(error, "Failed to load job detail."),
    });
    const retryMutation = useMutation({
        mutationFn: (job: ConsoleJob) => retryConsoleJob(job.id, job.source),
        onSuccess: (job) => {
            setSelected(job);
            refresh();
        },
        onError: (error) => toastError(error, "Retry failed."),
    });
    const cancelMutation = useMutation({
        mutationFn: (job: ConsoleJob) => cancelConsoleJob(job.id, job.source),
        onSuccess: (job) => {
            setSelected(job);
            setCancelTarget(null);
            refresh();
        },
        onError: (error) => toastError(error, "Cancel failed."),
    });

    return {
        status,
        setStatus,
        jobType,
        setJobType,
        queue,
        setQueue,
        projectId,
        setProjectId,
        failedOnly,
        setFailedOnly,
        selected,
        setSelected,
        cancelTarget,
        setCancelTarget,
        listQuery,
        detailMutation,
        retryMutation,
        cancelMutation,
    };
}

export type AdminJobsModel = ReturnType<typeof useAdminJobs>;

export function jobStateColor(
    state: string
): "default" | "success" | "warning" | "error" | "info" {
    if (state === "succeeded") return "success";
    if (state === "failed" || state === "stale") return "error";
    if (state === "running" || state === "retrying") return "warning";
    if (state === "cancelled") return "default";
    return "info";
}

/**
 * Compatibility wrapper around generated Jobs OpenAPI clients.
 * Prefer importing from here in features; do not reintroduce raw path strings.
 */
import {
    cancelConsoleJobApiV1AdminJobsJobIdCancelPost,
    getConsoleJobApiV1AdminJobsJobIdGet,
    listConsoleJobsApiV1AdminJobsGet,
    retryConsoleJobApiV1AdminJobsJobIdRetryPost,
} from "../generated/endpoints/jobs/jobs";
import type {
    JobConsoleItemResponse,
    JobsConsoleListResponse,
    ListConsoleJobsApiV1AdminJobsGetParams,
} from "../generated/models";

export type ConsoleJob = JobConsoleItemResponse;
export type ConsoleJobList = JobsConsoleListResponse;

export async function listConsoleJobs(
    params?: ListConsoleJobsApiV1AdminJobsGetParams
): Promise<ConsoleJobList> {
    return listConsoleJobsApiV1AdminJobsGet(params);
}

export async function getConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    return getConsoleJobApiV1AdminJobsJobIdGet(
        jobId,
        source ? { source } : undefined
    );
}

export async function retryConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    return retryConsoleJobApiV1AdminJobsJobIdRetryPost(
        jobId,
        source ? { source } : undefined
    );
}

export async function cancelConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    return cancelConsoleJobApiV1AdminJobsJobIdCancelPost(
        jobId,
        source ? { source } : undefined
    );
}

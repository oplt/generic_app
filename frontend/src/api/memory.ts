/**
 * Compatibility wrapper around generated Memory OpenAPI clients.
 * End-user privacy controls only — no embedding/vector internals.
 */
import {
    deleteMemoryApiV1MemoryMemoryIdDelete,
    listMemoriesApiV1MemoryGet,
} from "../generated/endpoints/memory/memory";
import type {
    ListMemoriesApiV1MemoryGetParams,
    MemoryItemResponse,
    PaginatedResponseMemoryItemResponse,
} from "../generated/models";

export type MemoryItem = MemoryItemResponse;
export type MemoryListResponse = PaginatedResponseMemoryItemResponse;

export async function listMyMemories(
    params?: ListMemoriesApiV1MemoryGetParams
): Promise<MemoryListResponse> {
    return listMemoriesApiV1MemoryGet(params);
}

export async function deleteMyMemory(memoryId: string): Promise<void> {
    await deleteMemoryApiV1MemoryMemoryIdDelete(memoryId);
}

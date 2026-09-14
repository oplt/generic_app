/**
 * Profile API — wraps the generated OpenAPI client where the wire contract is typed.
 * Prefer importing types from `../generated/models` for new code.
 */
import { apiFetch } from "./client";
import {
    deleteAvatarApiV1ProfileAvatarDelete,
    getProfileApiV1ProfileGet,
    updateProfileApiV1ProfilePut,
} from "../generated/endpoints/profile/profile";
import type { ProfileResponse, ProfileUpdate } from "../generated/models";

/** @deprecated Prefer `ProfileResponse` from generated models. */
export type Profile = ProfileResponse;

export type { ProfileResponse, ProfileUpdate };

export async function getProfile(): Promise<ProfileResponse> {
    return getProfileApiV1ProfileGet();
}

export async function updateProfile(payload: ProfileUpdate): Promise<ProfileResponse> {
    return updateProfileApiV1ProfilePut(payload);
}

/**
 * Multipart upload: OpenAPI marks the file as `string` (binary), so we keep a
 * hand-written FormData call and still return the generated response type.
 */
export async function uploadAvatar(file: File): Promise<ProfileResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<ProfileResponse>("/profile/avatar", {
        method: "POST",
        body: formData,
    });
}

export async function deleteAvatar(): Promise<void> {
    return deleteAvatarApiV1ProfileAvatarDelete();
}

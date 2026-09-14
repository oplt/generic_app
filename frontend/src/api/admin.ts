/**
 * Compatibility wrapper around generated Admin user OpenAPI clients.
 * Policy helpers live in `./policy` and are re-exported for existing imports.
 */
import {
    listUsersApiV1AdminUsersGet,
    updateUserStatusApiV1AdminUsersUserIdStatusPatch,
} from "../generated/endpoints/admin/admin";
import type {
    AdminUserListResponse as GeneratedAdminUserListResponse,
    AdminUserResponse,
    ListUsersApiV1AdminUsersGetParams,
} from "../generated/models";

export type AdminUser = AdminUserResponse;
export type AdminUserListResponse = GeneratedAdminUserListResponse;

export async function listAdminUsers(
    params?: ListUsersApiV1AdminUsersGetParams
): Promise<AdminUserListResponse> {
    return listUsersApiV1AdminUsersGet(params);
}

export async function updateUserStatus(
    userId: string,
    payload: { is_active: boolean }
): Promise<AdminUser> {
    return updateUserStatusApiV1AdminUsersUserIdStatusPatch(userId, payload);
}

export {
    assignPolicyRole,
    listPolicyPermissions,
    listPolicyRoles,
    listUserRoleAssignments,
    revokePolicyRole,
    type PolicyPermission,
    type PolicyRole,
    type RoleAssignment,
} from "./policy";

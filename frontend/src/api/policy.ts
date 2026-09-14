/**
 * Compatibility wrapper around generated Policy OpenAPI clients.
 */
import {
    assignRoleApiV1PolicyRoleAssignmentsPost,
    listRolesApiV1PolicyRolesGet,
    listUserRoleAssignmentsApiV1PolicyUsersUserIdRoleAssignmentsGet,
    revokeRoleApiV1PolicyRoleAssignmentsDelete,
} from "../generated/endpoints/policy/policy";
import type {
    RoleAssignmentCreate,
    RoleAssignmentResponse,
    RoleResponse,
    RevokeRoleApiV1PolicyRoleAssignmentsDeleteParams,
} from "../generated/models";

export type PolicyRole = RoleResponse;
export type RoleAssignment = RoleAssignmentResponse;

export async function listPolicyRoles(): Promise<PolicyRole[]> {
    return listRolesApiV1PolicyRolesGet();
}

export async function listUserRoleAssignments(userId: string): Promise<RoleAssignment[]> {
    return listUserRoleAssignmentsApiV1PolicyUsersUserIdRoleAssignmentsGet(userId);
}

export async function assignPolicyRole(
    payload: RoleAssignmentCreate
): Promise<RoleAssignment> {
    return assignRoleApiV1PolicyRoleAssignmentsPost(payload);
}

export async function revokePolicyRole(
    params: RevokeRoleApiV1PolicyRoleAssignmentsDeleteParams
): Promise<void> {
    await revokeRoleApiV1PolicyRoleAssignmentsDelete(params);
}

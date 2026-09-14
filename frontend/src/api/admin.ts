import { apiFetch } from "./client";

export type AdminUser = {
    id: string;
    email: string;
    full_name: string | null;
    is_verified: boolean;
    is_active: boolean;
    created_at: string;
    roles: string[];
};

export type AdminUserListResponse = {
    items: AdminUser[];
    total: number;
    page: number;
    page_size: number;
};

export async function listAdminUsers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
}): Promise<AdminUserListResponse> {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.search) qs.set("search", params.search);
    return apiFetch(`/admin/users?${qs.toString()}`);
}

export async function updateUserStatus(
    userId: string,
    payload: { is_active: boolean }
): Promise<AdminUser> {
    return apiFetch(`/admin/users/${userId}/status`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export type PolicyRole = {
    id: string;
    key: string;
    name: string;
    description: string;
    scope_type: string;
    is_system: boolean;
    permissions: string[];
};

export type RoleAssignment = {
    id: string;
    user_id: string;
    role_key: string;
    role_name: string;
    scope_type: string;
    organization_id: string | null;
    project_id: string | null;
    created_at: string;
};

export async function listPolicyRoles(): Promise<PolicyRole[]> {
    return apiFetch("/policy/roles");
}

export async function listUserRoleAssignments(userId: string): Promise<RoleAssignment[]> {
    return apiFetch(`/policy/users/${userId}/role-assignments`);
}

export async function assignPolicyRole(payload: {
    user_id: string;
    role_key: string;
    organization_id?: string | null;
    project_id?: string | null;
}): Promise<RoleAssignment> {
    return apiFetch("/policy/role-assignments", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function revokePolicyRole(params: {
    user_id: string;
    role_key: string;
    organization_id?: string | null;
    project_id?: string | null;
}): Promise<void> {
    const qs = new URLSearchParams();
    qs.set("user_id", params.user_id);
    qs.set("role_key", params.role_key);
    if (params.organization_id) qs.set("organization_id", params.organization_id);
    if (params.project_id) qs.set("project_id", params.project_id);
    await apiFetch(`/policy/role-assignments?${qs.toString()}`, { method: "DELETE" });
}

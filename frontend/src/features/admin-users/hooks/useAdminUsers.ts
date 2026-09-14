import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    listAdminUsers,
    updateUserStatus,
    type AdminUser,
    type AdminUserListResponse,
} from "../../../api/admin";
import { queryKeys } from "../../../config/queryKeys";
import { useDebounce } from "../../../hooks/useDebounce";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

export type DirectoryTab = "users" | "access";

const PAGE_SIZE = 20;

export function useAdminUsers() {
    const queryClient = useQueryClient();
    const toastMutationError = useMutationErrorToast();
    const [tab, setTab] = useState<DirectoryTab>("users");
    const [search, setSearch] = useState("");
    const [page, setPage] = useState(0);
    const [rolesUser, setRolesUser] = useState<AdminUser | null>(null);
    const debouncedSearch = useDebounce(search, 300);
    const usersQueryKey = queryKeys.admin.users(page, debouncedSearch);

    const usersQuery = useQuery({
        queryKey: usersQueryKey,
        queryFn: () =>
            listAdminUsers({
                page: page + 1,
                page_size: PAGE_SIZE,
                search: debouncedSearch || undefined,
            }),
        enabled: tab === "users",
    });

    const statusMutation = useMutation({
        mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
            updateUserStatus(id, { is_active }),
        onMutate: async ({ id, is_active }) => {
            await queryClient.cancelQueries({ queryKey: queryKeys.admin.all });
            const previous = queryClient.getQueryData<AdminUserListResponse>(usersQueryKey);
            queryClient.setQueryData<AdminUserListResponse>(usersQueryKey, (old) =>
                old
                    ? {
                          ...old,
                          items: old.items.map((user) =>
                              user.id === id ? { ...user, is_active } : user
                          ),
                      }
                    : old
            );
            return { previous, queryKey: usersQueryKey };
        },
        onError: (mutationError, _vars, context) => {
            if (context?.previous) {
                queryClient.setQueryData(context.queryKey, context.previous);
            }
            toastMutationError(mutationError, "Failed to update user status.");
        },
        onSettled: () => void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all }),
    });

    function updateSearch(value: string) {
        setSearch(value);
        setPage(0);
    }

    const users = usersQuery.data?.items ?? [];

    return {
        tab,
        setTab,
        search,
        updateSearch,
        page,
        setPage,
        pageSize: PAGE_SIZE,
        rolesUser,
        setRolesUser,
        usersQuery,
        statusMutation,
        users,
        activeCount: users.filter((user) => user.is_active).length,
        verifiedCount: users.filter((user) => user.is_verified).length,
        total: usersQuery.data?.total ?? 0,
    };
}

export type AdminUsersModel = ReturnType<typeof useAdminUsers>;

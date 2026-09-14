import {
    type PropsWithChildren,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { logout as logoutRequest, me, type AuthUser } from "../../../api/auth";
import { clearUserScopedQueryState, queryKeys } from "../../../config/queryKeys";
import { QUERY_STALE_TIMES } from "../../../config/queryTiming";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }: PropsWithChildren) {
    const queryClient = useQueryClient();
    const {
        data: currentUser = null,
        isPending,
        isError,
    } = useQuery<AuthUser | null>({
        queryKey: queryKeys.auth.me,
        queryFn: me,
        retry: false,
        staleTime: QUERY_STALE_TIMES.userProfile,
    });

    const isAuthenticated = currentUser !== null;
    const isReady = !isPending || isError;

    async function logout() {
        // Clear local identity first so protected screens unmount immediately;
        // network logout must not keep the previous user's data visible.
        await clearUserScopedQueryState(queryClient);
        queryClient.setQueryData(queryKeys.auth.me, null);
        try {
            await logoutRequest();
        } catch {
            // Local logout still succeeds when the server/session is unavailable.
        } finally {
            // Catch responses that raced cancellation during the transition.
            await clearUserScopedQueryState(queryClient);
        }
    }

    function setAuthenticated(user: AuthUser) {
        queryClient.setQueryData(queryKeys.auth.me, user);
    }

    return (
        <AuthContext.Provider
            value={{
                isReady,
                isAuthenticated,
                isAdmin: currentUser?.is_admin ?? false,
                isMfaEnabled: currentUser?.mfa_enabled ?? false,
                currentUser,
                logout,
                setAuthenticated,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

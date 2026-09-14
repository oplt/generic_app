import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it } from "vitest";

import { AUTH_SESSION_EXPIRED_EVENT } from "../../../api/client";
import { queryKeys } from "../../../config/queryKeys";
import { useAuth } from "../../../hooks/useAuth";
import { AuthProvider } from "./AuthContext";

function AuthState() {
    const { isAuthenticated } = useAuth();
    return <span>{isAuthenticated ? "authenticated" : "signed-out"}</span>;
}

describe("AuthProvider session expiry", () => {
    const clients: QueryClient[] = [];

    afterEach(() => {
        for (const client of clients) client.clear();
        clients.length = 0;
    });

    it("clears local authentication when the shared refresh fails", async () => {
        const client = new QueryClient({
            defaultOptions: { queries: { retry: false } },
        });
        clients.push(client);
        client.setQueryData(queryKeys.auth.me, {
            id: "user-1",
            email: "user@example.com",
            full_name: null,
            is_verified: true,
            is_admin: false,
            mfa_enabled: false,
        });

        render(
            <QueryClientProvider client={client}>
                <AuthProvider>
                    <AuthState />
                </AuthProvider>
            </QueryClientProvider>,
        );
        expect(screen.getByText("authenticated")).toBeInTheDocument();

        act(() => window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT)));

        expect(await screen.findByText("signed-out")).toBeInTheDocument();
        expect(client.getQueryData(queryKeys.auth.me)).toBeNull();
    });
});

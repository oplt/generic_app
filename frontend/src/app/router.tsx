import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Box, Skeleton, Stack } from "@mui/material";
import { ModuleRouteGate } from "../components/guards/ModuleRouteGate";
import { ProtectedRoute } from "../components/guards/ProtectedRoute";
import { useAuth } from "../hooks/useAuth";
import { assertPageRegistryComplete, authPages, PAGE_REGISTRY, publicPages } from "./pageRegistry";

assertPageRegistryComplete();

const AppLayout = lazy(() =>
    import("../components/layout/AppLayout").then((module) => ({ default: module.AppLayout }))
);
const NotFoundPage = PAGE_REGISTRY["not_found"].component;

function PageLoader() {
    return (
        <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
            <Stack spacing={3}>
                <Skeleton variant="rounded" height={170} sx={{ borderRadius: 2 }} />
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                    <Skeleton variant="rounded" height={168} sx={{ borderRadius: 2, flex: 1 }} />
                </Stack>
                <Skeleton variant="rounded" height={260} sx={{ borderRadius: 5 }} />
            </Stack>
        </Box>
    );
}

function SuspensePage({ children }: { children: ReactNode }) {
    return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

function GatedPage({
    pageKey,
    moduleKey,
    children,
}: {
    pageKey: string;
    moduleKey?: string;
    children: ReactNode;
}) {
    return (
        <ModuleRouteGate pageKey={pageKey} moduleKey={moduleKey}>
            <SuspensePage>{children}</SuspensePage>
        </ModuleRouteGate>
    );
}

function renderAuthPage(pageKey: string) {
    const page = PAGE_REGISTRY[pageKey];
    const Component = page.component;
    const body = page.shell ? (
        <SuspensePage>
            <Component />
        </SuspensePage>
    ) : (
        <GatedPage pageKey={page.pageKey} moduleKey={page.moduleKey}>
            <Component />
        </GatedPage>
    );

    if (page.admin) {
        return body;
    }
    return body;
}

export function AppRouter() {
    const { isReady, isAuthenticated, isAdmin } = useAuth();

    return (
        <BrowserRouter>
            <Routes>
                {publicPages().map((page) => {
                    const Component = page.component;
                    return (
                        <Route
                            key={page.pageKey}
                            path={page.path}
                            element={
                                <SuspensePage>
                                    <Component />
                                </SuspensePage>
                            }
                        />
                    );
                })}

                <Route
                    element={
                        <ProtectedRoute isReady={isReady} isAuthenticated={isAuthenticated}>
                            <Suspense fallback={<PageLoader />}>
                                <AppLayout />
                            </Suspense>
                        </ProtectedRoute>
                    }
                >
                    {authPages()
                        .filter((page) => !page.admin)
                        .map((page) => (
                            <Route
                                key={page.pageKey}
                                path={page.path}
                                element={renderAuthPage(page.pageKey)}
                            />
                        ))}

                    <Route path="/knowledge" element={<Navigate to="/knowledge-chat" replace />} />
                    {/* <generic-app:routes> */}
                    {/* </generic-app:routes> */}

                    {authPages()
                        .filter((page) => page.admin)
                        .map((page) => {
                            const Component = page.component;
                            return (
                                <Route
                                    key={page.pageKey}
                                    path={page.path}
                                    element={
                                        <ProtectedRoute
                                            isReady={isReady}
                                            isAuthenticated={isAuthenticated}
                                            isAdmin={isAdmin}
                                            requireAdmin
                                        >
                                            <GatedPage pageKey={page.pageKey} moduleKey={page.moduleKey}>
                                                <Component />
                                            </GatedPage>
                                        </ProtectedRoute>
                                    }
                                />
                            );
                        })}

                    <Route path="/app" element={<Navigate to="/dashboard" replace />} />
                </Route>

                <Route
                    path="*"
                    element={
                        <SuspensePage>
                            <NotFoundPage />
                        </SuspensePage>
                    }
                />
            </Routes>
        </BrowserRouter>
    );
}

import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Box, Skeleton, Stack } from "@mui/material";
import { ModuleRouteGate } from "../components/guards/ModuleRouteGate";
import { ProtectedRoute } from "../components/guards/ProtectedRoute";
import { useAuth } from "../hooks/useAuth";

const AuthHomePage = lazy(() => import("../features/auth/views/AuthHomeView"));
const AppLayout = lazy(() =>
    import("../components/layout/AppLayout").then((module) => ({ default: module.AppLayout }))
);
const DashboardPage = lazy(() => import("../features/dashboard/views/DashboardView"));
const CalendarPage = lazy(() => import("../features/calendar/views/CalendarView"));
const ProjectsPage = lazy(() => import("../features/projects/views/ProjectsView"));
const ProjectDetailPage = lazy(() => import("../features/projects/views/ProjectDetailView"));
const PlatformPage = lazy(() => import("../features/platform/views/PlatformView"));
const ProfilePage = lazy(() => import("../features/profile/views/ProfileView"));
const NotificationsPage = lazy(() => import("../features/notifications/views/NotificationsView"));
const ObservabilityPage = lazy(() => import("../features/observability/views/ObservabilityView"));
const ResetPasswordPage = lazy(() => import("../features/auth/views/ResetPasswordView"));
const VerifyEmailPage = lazy(() => import("../features/auth/views/VerifyEmailView"));
const AdminUsersPage = lazy(() => import("../features/admin-users/views/AdminUsersView"));
const AdminPlatformPage = lazy(() => import("../features/platform-admin/views/AdminPlatformView"));
const AdminSettingsPage = lazy(() => import("../features/settings-admin/views/AdminSettingsView"));
const AdminRagIndexesPage = lazy(
    () => import("../features/admin-rag/views/AdminRagIndexesView")
);
const AdminRagEvaluationPage = lazy(
    () => import("../features/admin-rag/views/AdminRagEvaluationView")
);
const AdminJobsPage = lazy(() => import("../features/admin-jobs/views/AdminJobsView"));
const AdminDiagnosticsPage = lazy(
    () => import("../features/admin-diagnostics/views/AdminDiagnosticsView")
);
const AiStudioPage = lazy(() => import("../features/ai/views/AiStudioView"));
const KnowledgeChatPage = lazy(() => import("../features/chat/views/KnowledgeChatView"));
// <generic-app:lazy-imports>
// </generic-app:lazy-imports>

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

function SuspensePage({ children }: { children: React.ReactNode }) {
    return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

function GatedPage({
    pageKey,
    moduleKey,
    children,
}: {
    pageKey: string;
    moduleKey?: string;
    children: React.ReactNode;
}) {
    return (
        <ModuleRouteGate pageKey={pageKey} moduleKey={moduleKey}>
            <SuspensePage>{children}</SuspensePage>
        </ModuleRouteGate>
    );
}

export function AppRouter() {
    const { isReady, isAuthenticated, isAdmin } = useAuth();

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<SuspensePage><AuthHomePage /></SuspensePage>} />
                <Route path="/reset-password" element={<SuspensePage><ResetPasswordPage /></SuspensePage>} />
                <Route path="/verify-email" element={<SuspensePage><VerifyEmailPage /></SuspensePage>} />

                <Route
                    element={
                        <ProtectedRoute isReady={isReady} isAuthenticated={isAuthenticated}>
                            <Suspense fallback={<PageLoader />}>
                                <AppLayout />
                            </Suspense>
                        </ProtectedRoute>
                    }
                >
                    <Route path="/dashboard" element={<SuspensePage><DashboardPage /></SuspensePage>} />
                    <Route
                        path="/calendar"
                        element={
                            <GatedPage pageKey="calendar.main" moduleKey="calendar">
                                <CalendarPage />
                            </GatedPage>
                        }
                    />
                    <Route path="/projects" element={<SuspensePage><ProjectsPage /></SuspensePage>} />
                    <Route path="/projects/:projectId" element={<SuspensePage><ProjectDetailPage /></SuspensePage>} />
                    <Route path="/platform" element={<SuspensePage><PlatformPage /></SuspensePage>} />
                    <Route
                        path="/ai"
                        element={
                            <GatedPage pageKey="ai.studio" moduleKey="ai">
                                <AiStudioPage />
                            </GatedPage>
                        }
                    />
                    <Route
                        path="/knowledge-chat"
                        element={
                            <GatedPage pageKey="chat.knowledge" moduleKey="chat">
                                <KnowledgeChatPage />
                            </GatedPage>
                        }
                    />
                    <Route path="/knowledge" element={<Navigate to="/knowledge-chat" replace />} />
                    <Route path="/observability" element={<SuspensePage><ObservabilityPage /></SuspensePage>} />
                    <Route path="/profile" element={<SuspensePage><ProfilePage /></SuspensePage>} />
                    <Route path="/notifications" element={<SuspensePage><NotificationsPage /></SuspensePage>} />
                    {/* <generic-app:routes> */}
                    {/* </generic-app:routes> */}
                    <Route
                        path="/admin/users"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <SuspensePage><AdminUsersPage /></SuspensePage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/platform"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <SuspensePage><AdminPlatformPage /></SuspensePage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/rag-indexes"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <GatedPage pageKey="rag.admin.indexes" moduleKey="rag">
                                    <AdminRagIndexesPage />
                                </GatedPage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/rag/evaluation"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <GatedPage pageKey="rag.admin.evaluation" moduleKey="rag">
                                    <AdminRagEvaluationPage />
                                </GatedPage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/jobs"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <GatedPage pageKey="jobs.admin.console" moduleKey="jobs">
                                    <AdminJobsPage />
                                </GatedPage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/diagnostics"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <GatedPage pageKey="diagnostics.admin" moduleKey="diagnostics">
                                    <AdminDiagnosticsPage />
                                </GatedPage>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/admin/settings"
                        element={
                            <ProtectedRoute
                                isReady={isReady}
                                isAuthenticated={isAuthenticated}
                                isAdmin={isAdmin}
                                requireAdmin
                            >
                                <SuspensePage><AdminSettingsPage /></SuspensePage>
                            </ProtectedRoute>
                        }
                    />
                    <Route path="/app" element={<Navigate to="/dashboard" replace />} />
                </Route>

                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

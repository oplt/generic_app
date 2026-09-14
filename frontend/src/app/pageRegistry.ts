import { lazy, type ComponentType, type LazyExoticComponent } from "react";

import pageKeys from "./pageKeys.json";

export type PageRegistration = {
    pageKey: string;
    path: string;
    component: LazyExoticComponent<ComponentType<unknown>>;
    /** Public unauthenticated route */
    public?: boolean;
    /** Requires authenticated shell (AppLayout) */
    auth?: boolean;
    /** Requires admin guard in addition to auth */
    admin?: boolean;
    /** Manifest module key for ModuleRouteGate (omit for shell-only pages) */
    moduleKey?: string;
    /** When true, skip module gate (always-on authenticated shell page) */
    shell?: boolean;
};

function page(
    pageKey: string,
    path: string,
    // Lazy route modules commonly export typed props; registry only needs a component.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- lazy page props vary by view
    loader: () => Promise<{ default: ComponentType<any> }>,
    opts: Omit<PageRegistration, "pageKey" | "path" | "component"> = {}
): PageRegistration {
    return {
        pageKey,
        path,
        component: lazy(loader) as LazyExoticComponent<ComponentType<unknown>>,
        ...opts,
    };
}

/**
 * Trusted frontend allow-list: page_key → lazy component.
 * Backend manifests declare which page_keys are active; they never supply import paths.
 */
export const PAGE_REGISTRY: Record<string, PageRegistration> = Object.fromEntries(
    [
        page("auth.home", "/", () => import("../features/auth/views/AuthHomeView"), {
            public: true,
        }),
        page(
            "auth.reset_password",
            "/reset-password",
            () => import("../features/auth/views/ResetPasswordView"),
            { public: true }
        ),
        page(
            "auth.verify_email",
            "/verify-email",
            () => import("../features/auth/views/VerifyEmailView"),
            { public: true }
        ),
        page(
            "dashboard.main",
            "/dashboard",
            () => import("../features/dashboard/views/DashboardView"),
            { auth: true, shell: true }
        ),
        page(
            "projects.list",
            "/projects",
            () => import("../features/projects/views/ProjectsView"),
            { auth: true, moduleKey: "projects" }
        ),
        page(
            "projects.detail",
            "/projects/:projectId",
            () => import("../features/projects/views/ProjectDetailView"),
            { auth: true, moduleKey: "projects" }
        ),
        page(
            "calendar.main",
            "/calendar",
            () => import("../features/calendar/views/CalendarView"),
            { auth: true, moduleKey: "calendar" }
        ),
        page(
            "platform.workspace",
            "/platform",
            () => import("../features/platform/views/PlatformView"),
            { auth: true, moduleKey: "platform" }
        ),
        page(
            "ai.studio",
            "/ai",
            () => import("../features/ai/views/AiStudioView"),
            { auth: true, moduleKey: "ai" }
        ),
        page(
            "chat.knowledge",
            "/knowledge-chat",
            () => import("../features/chat/views/KnowledgeChatView"),
            { auth: true, moduleKey: "chat" }
        ),
        page(
            "observability.main",
            "/observability",
            () => import("../features/observability/views/ObservabilityView"),
            { auth: true, moduleKey: "observability" }
        ),
        page(
            "profile.settings",
            "/profile",
            () => import("../features/profile/views/ProfileView"),
            { auth: true, moduleKey: "profile" }
        ),
        page(
            "notifications.inbox",
            "/notifications",
            () => import("../features/notifications/views/NotificationsView"),
            { auth: true, moduleKey: "notifications" }
        ),
        page(
            "admin.users",
            "/admin/users",
            () => import("../features/admin-users/views/AdminUsersView"),
            { auth: true, admin: true, moduleKey: "admin" }
        ),
        page(
            "platform.admin",
            "/admin/platform",
            () => import("../features/platform-admin/views/AdminPlatformView"),
            { auth: true, admin: true, moduleKey: "platform" }
        ),
        page(
            "settings.admin",
            "/admin/settings",
            () => import("../features/settings-admin/views/AdminSettingsView"),
            { auth: true, admin: true, moduleKey: "settings" }
        ),
        page(
            "rag.admin.indexes",
            "/admin/rag-indexes",
            () => import("../features/admin-rag/views/AdminRagIndexesView"),
            { auth: true, admin: true, moduleKey: "rag" }
        ),
        page(
            "rag.admin.evaluation",
            "/admin/rag/evaluation",
            () => import("../features/admin-rag/views/AdminRagEvaluationView"),
            { auth: true, admin: true, moduleKey: "rag" }
        ),
        page(
            "jobs.admin.console",
            "/admin/jobs",
            () => import("../features/admin-jobs/views/AdminJobsView"),
            { auth: true, admin: true, moduleKey: "jobs" }
        ),
        page(
            "diagnostics.admin",
            "/admin/diagnostics",
            () => import("../features/admin-diagnostics/views/AdminDiagnosticsView"),
            { auth: true, admin: true, moduleKey: "diagnostics" }
        ),
        page(
            "not_found",
            "*",
            () => import("../features/shell/views/NotFoundView"),
            { public: true }
        ),
        // <generic-app:page-registry>
        // </generic-app:page-registry>
    ].map((entry) => [entry.pageKey, entry])
);

export const REGISTERED_PAGE_KEYS: readonly string[] = pageKeys as string[];

export function assertPageRegistryComplete(): void {
    const missing = REGISTERED_PAGE_KEYS.filter((key) => !(key in PAGE_REGISTRY));
    const extra = Object.keys(PAGE_REGISTRY).filter(
        (key) => !REGISTERED_PAGE_KEYS.includes(key)
    );
    if (missing.length || extra.length) {
        throw new Error(
            `pageRegistry drift: missing=${missing.join(",") || "∅"} extra=${extra.join(",") || "∅"}`
        );
    }
}

export const publicPages = () =>
    REGISTERED_PAGE_KEYS.map((key) => PAGE_REGISTRY[key]).filter((p) => p.public && p.pageKey !== "not_found");

export const authPages = () =>
    REGISTERED_PAGE_KEYS.map((key) => PAGE_REGISTRY[key]).filter((p) => p.auth);

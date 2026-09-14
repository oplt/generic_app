import { useMemo } from "react";

import { useAuth } from "./useAuth";
import { usePlatformMetadata } from "./usePlatformMetadata";

export type SettingsTab = {
    label: string;
    path: string;
};

type SettingsTabDefinition = SettingsTab & {
    requiresPlatformModule?: boolean;
    requiresAiModule?: boolean;
    requiresActiveModule?: string;
    adminOnly?: boolean;
};

const SETTINGS_TAB_DEFINITIONS: SettingsTabDefinition[] = [
    { label: "Profile", path: "/profile" },
    { label: "Platform", path: "/platform", requiresPlatformModule: true },
    { label: "AI Studio", path: "/ai", requiresAiModule: true },
    { label: "Observability", path: "/observability" },
    { label: "Settings", path: "/admin/settings", adminOnly: true },
    { label: "Users", path: "/admin/users", adminOnly: true },
    { label: "RAG Indexes", path: "/admin/rag-indexes", adminOnly: true, requiresActiveModule: "rag" },
    {
        label: "RAG Evaluation",
        path: "/admin/rag/evaluation",
        adminOnly: true,
        requiresActiveModule: "rag",
    },
    { label: "Jobs", path: "/admin/jobs", adminOnly: true, requiresActiveModule: "jobs" },
    {
        label: "Diagnostics",
        path: "/admin/diagnostics",
        adminOnly: true,
        requiresActiveModule: "diagnostics",
    },
    { label: "Platform Admin", path: "/admin/platform", adminOnly: true },
];

export function getVisibleSettingsTabs({
    isAdmin,
    hasUserPlatformModule,
    hasAiModule,
    activeModules,
}: {
    isAdmin: boolean;
    hasUserPlatformModule: boolean;
    hasAiModule: boolean;
    activeModules: Set<string>;
}): SettingsTab[] {
    return SETTINGS_TAB_DEFINITIONS.filter((item) => {
        if (item.adminOnly && !isAdmin) return false;
        if (item.requiresPlatformModule && !hasUserPlatformModule) return false;
        if (item.requiresAiModule && !hasAiModule) return false;
        if (item.requiresActiveModule && !activeModules.has(item.requiresActiveModule)) {
            return false;
        }
        return true;
    });
}

export function useSettingsTabs(): SettingsTab[] {
    const { isAdmin } = useAuth();
    const { data: platformMetadata } = usePlatformMetadata();
    const hasUserPlatformModule =
        platformMetadata?.module_catalog.some((item) => item.user_visible && item.enabled) ?? false;
    const activeModulesKey = (platformMetadata?.active_modules ?? []).join(",");
    const hasAiModule = (platformMetadata?.active_modules ?? []).includes("ai");

    return useMemo(() => {
        const activeModules = new Set(
            activeModulesKey ? activeModulesKey.split(",") : []
        );
        return getVisibleSettingsTabs({
            isAdmin,
            hasUserPlatformModule,
            hasAiModule,
            activeModules,
        });
    }, [activeModulesKey, hasAiModule, hasUserPlatformModule, isAdmin]);
}

export function getActiveSettingsTab(
    pathname: string,
    tabs: SettingsTab[]
): SettingsTab | undefined {
    return [...tabs]
        .sort((left, right) => right.path.length - left.path.length)
        .find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));
}

export function isSettingsHubPath(pathname: string, tabs: SettingsTab[]): boolean {
    return getActiveSettingsTab(pathname, tabs) !== undefined;
}

export function getSettingsHubLabel(
    pathname: string,
    tabs: SettingsTab[]
): string | undefined {
    return getActiveSettingsTab(pathname, tabs)?.label;
}

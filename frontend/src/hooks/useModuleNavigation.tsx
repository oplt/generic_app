import { useMemo } from "react";
import {
    CalendarMonth as CalendarIcon,
    Dashboard as DashboardIcon,
    FolderOpen as ProjectsIcon,
    AutoAwesome as KnowledgeIcon,
    Settings as SettingsIcon,
} from "@mui/icons-material";
import type { ModuleNavEntry } from "../api/platform";
import type { NavItem } from "../components/layout/AppNavigation";
import { usePlatformMetadata } from "./usePlatformMetadata";
import { isSettingsHubPath, useSettingsTabs } from "./useSettingsTabs";

const ICON_MAP = {
    dashboard: <DashboardIcon />,
    projects: <ProjectsIcon />,
    knowledge: <KnowledgeIcon />,
    calendar: <CalendarIcon />,
    settings: <SettingsIcon />,
} as const;

function iconFor(name: string | null | undefined) {
    if (!name) return <DashboardIcon />;
    return ICON_MAP[name as keyof typeof ICON_MAP] ?? <DashboardIcon />;
}

/**
 * Compose workspace navigation from core entries plus module manifest contributions.
 * Backend ``module_nav`` is the authoritative allow-list for feature pages.
 */
export function useModuleNavigation(coreDomainPlural: string): NavItem[] {
    const { data: platformMetadata } = usePlatformMetadata();

    return useMemo(() => {
        const contributed = platformMetadata?.module_nav ?? [];
        const byPath = new Map<string, ModuleNavEntry>();
        for (const entry of contributed) {
            byPath.set(entry.path, entry);
        }

        const items: NavItem[] = [
            { label: "Dashboard", icon: <DashboardIcon />, path: "/dashboard", group: "workspace" },
        ];

        const projects = byPath.get("/projects");
        items.push({
            label: projects?.label === "Projects" ? coreDomainPlural : projects?.label ?? coreDomainPlural,
            icon: iconFor(projects?.icon ?? "projects"),
            path: "/projects",
            group: "workspace",
        });

        // Remaining workspace contributions from active modules (calendar, chat, …).
        const seen = new Set(items.map((item) => item.path));
        for (const entry of contributed) {
            if (entry.path === "/projects" || seen.has(entry.path)) continue;
            if (entry.group && entry.group !== "workspace") continue;
            items.push({
                label: entry.label,
                icon: iconFor(entry.icon),
                path: entry.path,
                group: "workspace",
            });
            seen.add(entry.path);
        }

        return items;
    }, [coreDomainPlural, platformMetadata?.module_nav]);
}

export function useSettingsNavItem(): NavItem {
    const settingsTabs = useSettingsTabs();
    return useMemo(
        () => ({
            label: "Settings",
            icon: <SettingsIcon />,
            path: "/profile",
            group: "workspace",
            isSelected: (pathname) => isSettingsHubPath(pathname, settingsTabs),
        }),
        [settingsTabs]
    );
}

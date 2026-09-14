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
 * Only allow-listed icon keys and server-provided paths are used (no dynamic imports).
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

        const knowledge = byPath.get("/knowledge-chat");
        if (knowledge) {
            items.push({
                label: knowledge.label,
                icon: iconFor(knowledge.icon),
                path: knowledge.path,
                group: knowledge.group || "workspace",
            });
        } else {
            // Fallback while older API responses omit module_nav.
            items.push({
                label: "Knowledge chat",
                icon: <KnowledgeIcon />,
                path: "/knowledge-chat",
                group: "workspace",
            });
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

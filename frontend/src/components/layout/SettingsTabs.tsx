import { useMemo } from "react";
import { Box, Tab, Tabs } from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";
import { alpha } from "@mui/material/styles";
import { useAuth } from "../../hooks/useAuth";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";

type SettingsTab = {
    label: string;
    path: string;
};

const BASE_TABS: Array<SettingsTab & { requiresPlatformModule?: boolean; requiresAiModule?: boolean; adminOnly?: boolean }> = [
    { label: "Profile", path: "/profile" },
    { label: "Platform", path: "/platform", requiresPlatformModule: true },
    { label: "AI Studio", path: "/ai", requiresAiModule: true },
    { label: "Observability", path: "/observability" },
    { label: "Settings", path: "/admin/settings", adminOnly: true },
    { label: "Users", path: "/admin/users", adminOnly: true },
    { label: "Platform Admin", path: "/admin/platform", adminOnly: true },
];

export function useSettingsTabs(): SettingsTab[] {
    const { isAdmin } = useAuth();
    const { data: platformMetadata } = usePlatformMetadata();
    const hasUserPlatformModule =
        platformMetadata?.module_catalog.some((item) => item.user_visible && item.enabled) ?? false;
    const hasAiModule =
        platformMetadata?.module_catalog.some((item) => item.key === "ai" && item.enabled) ?? false;

    return useMemo(
        () =>
            BASE_TABS.filter((item) => {
                if (item.adminOnly && !isAdmin) {
                    return false;
                }
                if (item.requiresPlatformModule && !hasUserPlatformModule) {
                    return false;
                }
                if (item.requiresAiModule && !hasAiModule) {
                    return false;
                }
                return true;
            }),
        [hasAiModule, hasUserPlatformModule, isAdmin]
    );
}

export function getActiveSettingsTab(pathname: string, tabs: SettingsTab[]): SettingsTab | undefined {
    return [...tabs]
        .sort((left, right) => right.path.length - left.path.length)
        .find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));
}

export function isSettingsHubPath(pathname: string, tabs: SettingsTab[]): boolean {
    return getActiveSettingsTab(pathname, tabs) !== undefined;
}

export function getSettingsHubLabel(pathname: string, tabs: SettingsTab[]): string | undefined {
    return getActiveSettingsTab(pathname, tabs)?.label;
}

export function SettingsTabs() {
    const location = useLocation();
    const navigate = useNavigate();
    const tabs = useSettingsTabs();
    const activePath = getActiveSettingsTab(location.pathname, tabs)?.path ?? tabs[0]?.path ?? "/profile";

    if (tabs.length === 0) {
        return null;
    }

    return (
        <Box
            sx={(theme) => ({
                p: 0.75,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.paper, 0.82),
            })}
        >
            <Tabs
                value={activePath}
                onChange={(_, value: string) => navigate(value)}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
            >
                {tabs.map((item) => (
                    <Tab key={item.path} value={item.path} label={item.label} />
                ))}
            </Tabs>
        </Box>
    );
}

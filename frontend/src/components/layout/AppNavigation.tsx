import type { ReactNode } from "react";
import {
    DarkMode as DarkModeIcon,
    LightMode as LightModeIcon,
    SettingsBrightness as SystemModeIcon,
} from "@mui/icons-material";
import {
    IconButton,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Stack,
    Tooltip,
    Typography,
} from "@mui/material";
import { useColorMode } from "../../app/colorModeContext";

export type NavItem = {
    label: string;
    icon: ReactNode;
    path: string;
    group: "workspace";
    isSelected?: (pathname: string) => boolean;
};

export function ThemeToggle() {
    const { colorMode, setColorMode } = useColorMode();
    const cycle = () => {
        const next: Record<string, typeof colorMode> = {
            light: "dark",
            dark: "system",
            system: "light",
        };
        setColorMode(next[colorMode]);
    };
    const icon = colorMode === "light"
        ? <LightModeIcon fontSize="small" />
        : colorMode === "dark"
            ? <DarkModeIcon fontSize="small" />
            : <SystemModeIcon fontSize="small" />;

    return (
        <Tooltip title={`Theme: ${colorMode}`}>
            <IconButton onClick={cycle} size="small" aria-label="Cycle color theme">
                {icon}
            </IconButton>
        </Tooltip>
    );
}

export function NavBlock({
    title,
    items,
    currentPath,
    onNavigate,
    collapsed,
}: {
    title: string;
    items: NavItem[];
    currentPath: string;
    onNavigate: (path: string) => void;
    collapsed: boolean;
}) {
    if (items.length === 0) return null;

    return (
        <Stack spacing={1}>
            {!collapsed && <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2 }}>{title}</Typography>}
            <List disablePadding sx={{ display: "grid", gap: 0.75 }}>
                {items.map((item) => {
                    const selected = item.isSelected
                        ? item.isSelected(currentPath)
                        : item.path === "/dashboard"
                            ? currentPath === item.path
                            : currentPath.startsWith(item.path);
                    const itemButton = (
                        <ListItemButton
                            key={item.path}
                            selected={selected}
                            aria-current={selected ? "page" : undefined}
                            onClick={() => onNavigate(item.path)}
                            sx={collapsed ? { minHeight: 48, px: 1, justifyContent: "center" } : undefined}
                        >
                            <ListItemIcon sx={{ minWidth: collapsed ? "auto" : 40, justifyContent: "center" }}>
                                {item.icon}
                            </ListItemIcon>
                            {!collapsed && (
                                <ListItemText
                                    primary={item.label}
                                    secondary={selected ? "Current section" : undefined}
                                    secondaryTypographyProps={{ sx: { fontSize: "0.74rem" } }}
                                />
                            )}
                        </ListItemButton>
                    );
                    return collapsed
                        ? <Tooltip key={item.path} title={item.label} placement="right">{itemButton}</Tooltip>
                        : itemButton;
                })}
            </List>
        </Stack>
    );
}

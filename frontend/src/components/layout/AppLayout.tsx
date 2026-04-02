import { useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    AppBar,
    Avatar,
    Badge,
    Box,
    Button,
    Chip,
    Divider,
    Drawer,
    IconButton,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Menu,
    MenuItem,
    Stack,
    Toolbar,
    Tooltip,
    Typography,
    useMediaQuery,
} from "@mui/material";
import {
    AdminPanelSettings as AdminIcon,
    Dashboard as DashboardIcon,
    DarkMode as DarkModeIcon,
    FolderOpen as ProjectsIcon,
    LightMode as LightModeIcon,
    Logout as LogoutIcon,
    Menu as MenuIcon,
    Notifications as NotificationsIcon,
    Person as ProfileIcon,
    Settings as SettingsIcon,
    SettingsBrightness as SystemModeIcon,
    Extension as PlatformIcon,
} from "@mui/icons-material";
import { alpha, useTheme } from "@mui/material/styles";
import { useQuery } from "@tanstack/react-query";
import { useColorMode } from "../../app/colorModeContext";
import { getNotifications } from "../../api/notifications";
import { getProfile } from "../../api/profile";
import { getMe } from "../../api/users";
import { useAuth } from "../../hooks/useAuth";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { getInitials } from "../../utils/formatters";

const DRAWER_WIDTH = 288;

type NavItem = {
    label: string;
    icon: React.ReactNode;
    path: string;
    adminOnly?: boolean;
    badge?: number;
    group: "workspace" | "admin";
};

function ThemeToggle() {
    const { colorMode, setColorMode } = useColorMode();
    const cycle = () => {
        const next: Record<string, typeof colorMode> = { light: "dark", dark: "system", system: "light" };
        setColorMode(next[colorMode]);
    };
    const icon =
        colorMode === "light" ? <LightModeIcon fontSize="small" /> :
        colorMode === "dark" ? <DarkModeIcon fontSize="small" /> :
        <SystemModeIcon fontSize="small" />;

    return (
        <Tooltip title={`Theme: ${colorMode}`}>
            <IconButton onClick={cycle} size="small" sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                {icon}
            </IconButton>
        </Tooltip>
    );
}

function NavBlock({
    title,
    items,
    currentPath,
    onNavigate,
}: {
    title: string;
    items: NavItem[];
    currentPath: string;
    onNavigate: (path: string) => void;
}) {
    if (items.length === 0) {
        return null;
    }

    return (
        <Stack spacing={1}>
            <Typography variant="overline" color="text.secondary" sx={{ px: 1.5 }}>
                {title}
            </Typography>
            <List disablePadding sx={{ display: "grid", gap: 0.75 }}>
                {items.map((item) => {
                    const selected =
                        item.path === "/dashboard"
                            ? currentPath === item.path
                            : currentPath.startsWith(item.path);
                    return (
                        <ListItemButton key={item.path} selected={selected} onClick={() => onNavigate(item.path)}>
                            <ListItemIcon sx={{ minWidth: 40 }}>
                                {item.badge ? (
                                    <Badge badgeContent={item.badge} color="error">
                                        {item.icon}
                                    </Badge>
                                ) : (
                                    item.icon
                                )}
                            </ListItemIcon>
                            <ListItemText
                                primary={item.label}
                                secondary={selected ? "Current section" : undefined}
                                secondaryTypographyProps={{ sx: { fontSize: "0.74rem" } }}
                            />
                        </ListItemButton>
                    );
                })}
            </List>
        </Stack>
    );
}

export function AppLayout() {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
    const { logout, isAdmin } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    const { data: platformMetadata } = usePlatformMetadata();

    const { data: currentUser } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: notifications } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
        refetchInterval: 60_000,
    });
    const { data: profile } = useQuery({
        queryKey: ["profile"],
        queryFn: getProfile,
        staleTime: 5 * 60_000,
    });

    const unreadCount = notifications?.filter((notification) => !notification.is_read).length ?? 0;
    const appName = platformMetadata?.app_name ?? "Your App";
    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";
    const hasUserPlatformModule =
        platformMetadata?.module_catalog.some((item) => item.user_visible && item.enabled) ?? false;

    const navItems = useMemo<NavItem[]>(
        () => [
            { label: "Dashboard", icon: <DashboardIcon />, path: "/dashboard", group: "workspace" },
            { label: coreDomainPlural, icon: <ProjectsIcon />, path: "/projects", group: "workspace" },
            ...(hasUserPlatformModule
                ? [{ label: "Platform", icon: <PlatformIcon />, path: "/platform", group: "workspace" as const }]
                : []),
            {
                label: "Notifications",
                icon: <NotificationsIcon />,
                path: "/notifications",
                group: "workspace",
                badge: unreadCount || undefined,
            },
            { label: "Profile", icon: <ProfileIcon />, path: "/profile", group: "workspace" },
            { label: "Users", icon: <AdminIcon />, path: "/admin/users", adminOnly: true, group: "admin" },
            { label: "Platform Admin", icon: <PlatformIcon />, path: "/admin/platform", adminOnly: true, group: "admin" },
            { label: "Settings", icon: <SettingsIcon />, path: "/admin/settings", adminOnly: true, group: "admin" },
        ],
        [coreDomainPlural, hasUserPlatformModule, unreadCount]
    );

    const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);
    const currentItem = visibleNavItems.find((item) =>
        item.path === "/dashboard" ? location.pathname === item.path : location.pathname.startsWith(item.path)
    );
    const avatarLabel = getInitials(currentUser?.full_name, currentUser?.email);

    const drawerContent = (
        <Stack sx={{ height: "100%", p: 2 }}>
            <Box
                sx={(currentTheme) => ({
                    borderRadius: 4,
                    px: 2,
                    py: 2.25,
                    mb: 2,
                    border: `1px solid ${currentTheme.palette.divider}`,
                    background: `linear-gradient(155deg, ${alpha(currentTheme.palette.primary.main, currentTheme.palette.mode === "dark" ? 0.3 : 0.12)} 0%, ${alpha(
                        currentTheme.palette.secondary.main,
                        currentTheme.palette.mode === "dark" ? 0.18 : 0.08
                    )} 100%)`,
                })}
            >
                <Typography variant="overline" sx={{ color: "primary.main" }}>
                    Workspace
                </Typography>
                <Typography variant="h6" sx={{ mt: 0.5 }}>
                    {appName}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                    A sharper control center for your team, customers, and operations.
                </Typography>
                {platformMetadata?.module_pack && (
                    <Chip
                        label={`Pack: ${platformMetadata.module_pack}`}
                        size="small"
                        variant="outlined"
                        sx={{ mt: 1.5 }}
                    />
                )}
            </Box>

            <Stack spacing={2}>
                <NavBlock
                    title="Product"
                    items={visibleNavItems.filter((item) => item.group === "workspace")}
                    currentPath={location.pathname}
                    onNavigate={(path) => {
                        navigate(path);
                        setDrawerOpen(false);
                    }}
                />
                {isAdmin && (
                    <NavBlock
                        title="Administration"
                        items={visibleNavItems.filter((item) => item.group === "admin")}
                        currentPath={location.pathname}
                        onNavigate={(path) => {
                            navigate(path);
                            setDrawerOpen(false);
                        }}
                    />
                )}
            </Stack>

            <Box sx={{ flexGrow: 1 }} />

            <Box
                sx={(currentTheme) => ({
                    p: 2,
                    borderRadius: 4,
                    border: `1px solid ${currentTheme.palette.divider}`,
                    backgroundColor: alpha(currentTheme.palette.background.paper, 0.78),
                })}
            >
                <Stack spacing={1.5}>
                    <Stack direction="row" spacing={1.5} alignItems="center">
                        <Avatar
                            src={profile?.avatar_url ?? undefined}
                            sx={{ width: 44, height: 44 }}
                        >
                            {avatarLabel}
                        </Avatar>
                        <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" noWrap>
                                {currentUser?.full_name ?? "Your profile"}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" noWrap>
                                {currentUser?.email ?? "Signed in"}
                            </Typography>
                        </Box>
                    </Stack>
                    <Button variant="outlined" fullWidth onClick={() => navigate("/profile")}>
                        Manage profile
                    </Button>
                </Stack>
            </Box>
        </Stack>
    );

    return (
        <Box sx={{ minHeight: "100vh" }}>
            <AppBar
                position="fixed"
                elevation={0}
                sx={{
                    left: { md: `${DRAWER_WIDTH}px` },
                    width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
                    borderBottom: 1,
                    borderColor: "divider",
                    backgroundColor: alpha(theme.palette.background.default, theme.palette.mode === "dark" ? 0.82 : 0.78),
                    color: "text.primary",
                }}
            >
                <Toolbar sx={{ minHeight: { xs: 72, md: 80 }, px: { xs: 2, md: 3 } }}>
                    {isMobile && (
                        <IconButton edge="start" onClick={() => setDrawerOpen(true)} sx={{ mr: 1.25 }}>
                            <MenuIcon />
                        </IconButton>
                    )}
                    <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                            {appName}
                        </Typography>
                        <Typography variant="h6" noWrap>
                            {currentItem?.label ?? "Workspace"}
                        </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <ThemeToggle />
                        <Tooltip title="Notifications">
                            <IconButton onClick={() => navigate("/notifications")} sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                                <Badge badgeContent={unreadCount} color="error">
                                    <NotificationsIcon fontSize="small" />
                                </Badge>
                            </IconButton>
                        </Tooltip>
                        <IconButton onClick={(event) => setAnchorEl(event.currentTarget)} sx={{ p: 0.5 }}>
                            <Avatar
                                src={profile?.avatar_url ?? undefined}
                                sx={{ width: 38, height: 38 }}
                            >
                                {avatarLabel}
                            </Avatar>
                        </IconButton>
                    </Stack>
                    <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
                        <MenuItem
                            onClick={() => {
                                navigate("/profile");
                                setAnchorEl(null);
                            }}
                        >
                            <ListItemIcon>
                                <ProfileIcon fontSize="small" />
                            </ListItemIcon>
                            Profile
                        </MenuItem>
                        <Divider />
                        <MenuItem
                            onClick={() => {
                                logout();
                                navigate("/");
                                setAnchorEl(null);
                            }}
                        >
                            <ListItemIcon>
                                <LogoutIcon fontSize="small" />
                            </ListItemIcon>
                            Sign out
                        </MenuItem>
                    </Menu>
                </Toolbar>
            </AppBar>

            {isMobile ? (
                <Drawer
                    open={drawerOpen}
                    onClose={() => setDrawerOpen(false)}
                    ModalProps={{ keepMounted: true }}
                    sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
                >
                    {drawerContent}
                </Drawer>
            ) : (
                <Drawer
                    variant="permanent"
                    open
                    sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
                >
                    {drawerContent}
                </Drawer>
            )}

            <Box
                component="main"
                sx={{
                    minHeight: "100vh",
                    ml: { md: `${DRAWER_WIDTH}px` },
                    pt: { xs: "72px", md: "80px" },
                }}
            >
                <Outlet />
            </Box>
        </Box>
    );
}

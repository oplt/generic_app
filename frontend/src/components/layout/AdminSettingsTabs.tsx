import { Box, Tab, Tabs } from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";
import { alpha } from "@mui/material/styles";

const ADMIN_TABS = [
    { label: "Settings", path: "/admin/settings" },
    { label: "Users", path: "/admin/users" },
    { label: "Platform Admin", path: "/admin/platform" },
];

export function AdminSettingsTabs() {
    const location = useLocation();
    const navigate = useNavigate();
    const activePath =
        ADMIN_TABS.find((item) => location.pathname.startsWith(item.path))?.path ?? "/admin/settings";

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
                {ADMIN_TABS.map((item) => (
                    <Tab key={item.path} value={item.path} label={item.label} />
                ))}
            </Tabs>
        </Box>
    );
}

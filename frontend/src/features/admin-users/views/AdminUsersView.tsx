import { Tab, Tabs } from "@mui/material";
import { AdminSettingsTabs } from "../../../components/layout/AdminSettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { AccessControlPanels } from "../components/AccessControlPanels";
import { UserRolesDialog } from "../components/UserRolesDialog";
import { UsersDirectoryPanel } from "../components/UsersDirectoryPanel";
import { useAdminUsers, type DirectoryTab } from "../hooks/useAdminUsers";

export default function AdminUsersPage() {
    const m = useAdminUsers();

    return (
        <PageShell maxWidth="xl">
            <AdminSettingsTabs />

            <Tabs
                value={m.tab}
                onChange={(_event, value: DirectoryTab) => m.setTab(value)}
                sx={{ mb: 2 }}
                aria-label="Admin users and access"
            >
                <Tab label="Users" value="users" />
                <Tab label="Access" value="access" />
            </Tabs>

            {m.tab === "access" ? <AccessControlPanels /> : <UsersDirectoryPanel m={m} />}

            <UserRolesDialog
                user={m.rolesUser}
                open={Boolean(m.rolesUser)}
                onClose={() => m.setRolesUser(null)}
            />
        </PageShell>
    );
}

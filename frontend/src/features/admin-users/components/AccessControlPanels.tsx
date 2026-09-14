import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Chip,
    CircularProgress,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import { listPolicyPermissions, listPolicyRoles } from "../../../api/policy";
import { EmptyState } from "../../../components/ui/EmptyState";
import { InfoTooltip } from "../../../components/ui/InfoTooltip";
import { SectionCard } from "../../../components/ui/SectionCard";
import { queryKeys } from "../../../config/queryKeys";

function PermissionKey({ permissionKey, description }: { permissionKey: string; description?: string }) {
    return (
        <Stack direction="row" spacing={0.5} alignItems="center" component="span">
            <Typography component="span" variant="body2" sx={{ fontFamily: "ui-monospace, monospace" }}>
                {permissionKey}
            </Typography>
            {description ? (
                <InfoTooltip title={description} label={`About ${permissionKey}`} />
            ) : null}
        </Stack>
    );
}

/** Compact Roles + Permissions catalogs (Access Control under Admin Users). */
export function AccessControlPanels() {
    const rolesQuery = useQuery({
        queryKey: queryKeys.admin.policyRoles,
        queryFn: listPolicyRoles,
    });
    const permissionsQuery = useQuery({
        queryKey: queryKeys.admin.policyPermissions,
        queryFn: listPolicyPermissions,
    });

    const permissionHelp = new Map(
        (permissionsQuery.data ?? []).map((item) => [item.key, item.description])
    );

    return (
        <Box
            sx={{
                display: "grid",
                gap: 2,
                gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.2fr) minmax(0, 0.8fr)" },
            }}
        >
            <SectionCard title="Roles" description="Built-in capability packs. Assign from a user row.">
                {rolesQuery.isLoading ? (
                    <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                        <CircularProgress size={28} />
                    </Box>
                ) : (rolesQuery.data ?? []).length === 0 ? (
                    <EmptyState title="No roles" description="Policy catalog is empty." />
                ) : (
                    <TableContainer>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>Role</TableCell>
                                    <TableCell>Scope</TableCell>
                                    <TableCell>Permissions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {(rolesQuery.data ?? []).map((role) => (
                                    <TableRow key={role.key} hover>
                                        <TableCell>
                                            <Typography variant="subtitle2">{role.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {role.key}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Chip size="small" label={role.scope_type} />
                                        </TableCell>
                                        <TableCell>
                                            <Stack direction="row" flexWrap="wrap" gap={0.5}>
                                                {(role.permissions ?? []).map((permissionKey) => (
                                                    <Chip
                                                        key={permissionKey}
                                                        size="small"
                                                        variant="outlined"
                                                        label={
                                                            <PermissionKey
                                                                permissionKey={permissionKey}
                                                                description={permissionHelp.get(permissionKey)}
                                                            />
                                                        }
                                                    />
                                                ))}
                                            </Stack>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                )}
            </SectionCard>

            <SectionCard title="Permissions" description="Stable capability keys. Hover for detail.">
                {permissionsQuery.isLoading ? (
                    <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                        <CircularProgress size={28} />
                    </Box>
                ) : (permissionsQuery.data ?? []).length === 0 ? (
                    <EmptyState title="No permissions" description="Permission catalog is empty." />
                ) : (
                    <TableContainer>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>Key</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {(permissionsQuery.data ?? []).map((permission) => (
                                    <TableRow key={permission.key} hover>
                                        <TableCell>
                                            <PermissionKey
                                                permissionKey={permission.key}
                                                description={permission.description}
                                            />
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                )}
            </SectionCard>
        </Box>
    );
}

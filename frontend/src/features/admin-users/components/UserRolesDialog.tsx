import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Stack,
    Typography,
} from "@mui/material";
import {
    assignPolicyRole,
    listPolicyRoles,
    listUserRoleAssignments,
    revokePolicyRole,
} from "../../../api/policy";
import type { AdminUser } from "../../../api/admin";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

type Props = {
    user: AdminUser | null;
    open: boolean;
    onClose: () => void;
};

/** Assign/revoke system-scoped roles; org/project scopes stay membership-driven. */
export function UserRolesDialog({ user, open, onClose }: Props) {
    const queryClient = useQueryClient();
    const toastMutationError = useMutationErrorToast();
    const userId = user?.id ?? "";

    const rolesQuery = useQuery({
        queryKey: queryKeys.admin.policyRoles,
        queryFn: listPolicyRoles,
        enabled: open,
    });
    const assignmentsQuery = useQuery({
        queryKey: queryKeys.admin.userRoleAssignments(userId),
        queryFn: () => listUserRoleAssignments(userId),
        enabled: open && Boolean(userId),
    });

    const assignMutation = useMutation({
        mutationFn: (roleKey: string) =>
            assignPolicyRole({
                user_id: userId,
                role_key: roleKey,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({
                queryKey: queryKeys.admin.userRoleAssignments(userId),
            });
            await queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
        },
        onError: (error) => toastMutationError(error, "Failed to assign role."),
    });

    const revokeMutation = useMutation({
        mutationFn: (roleKey: string) =>
            revokePolicyRole({
                user_id: userId,
                role_key: roleKey,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({
                queryKey: queryKeys.admin.userRoleAssignments(userId),
            });
            await queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
        },
        onError: (error) => toastMutationError(error, "Failed to revoke role."),
    });

    const systemRoles = (rolesQuery.data ?? []).filter((role) => role.scope_type === "system");
    const assignedKeys = new Set((assignmentsQuery.data ?? []).map((row) => row.role_key));
    const busy = assignMutation.isPending || revokeMutation.isPending;

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>Roles — {user?.email ?? "user"}</DialogTitle>
            <DialogContent>
                {rolesQuery.isLoading || assignmentsQuery.isLoading ? (
                    <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                        <CircularProgress size={28} />
                    </Box>
                ) : (
                    <Stack spacing={2} sx={{ pt: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                            System roles are assigned here. Organization and project roles follow
                            membership defaults.
                        </Typography>
                        {systemRoles.map((role) => {
                            const assigned = assignedKeys.has(role.key);
                            return (
                                <Box
                                    key={role.key}
                                    sx={(theme) => ({
                                        p: 2,
                                        borderRadius: 2,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Typography variant="subtitle2">{role.name}</Typography>
                                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                                        {role.description}
                                    </Typography>
                                    <Button
                                        size="small"
                                        variant={assigned ? "outlined" : "contained"}
                                        color={assigned ? "warning" : "primary"}
                                        disabled={busy}
                                        onClick={() =>
                                            assigned
                                                ? revokeMutation.mutate(role.key)
                                                : assignMutation.mutate(role.key)
                                        }
                                    >
                                        {assigned ? `Revoke ${role.name}` : `Grant ${role.name}`}
                                    </Button>
                                </Box>
                            );
                        })}
                        {(assignmentsQuery.data ?? []).length > 0 && (
                            <Stack spacing={0.5}>
                                <Typography variant="caption" color="text.secondary">
                                    Current assignments
                                </Typography>
                                {(assignmentsQuery.data ?? []).map((assignment) => (
                                    <Typography key={assignment.id} variant="body2">
                                        {assignment.role_name} ({assignment.scope_type})
                                        {assignment.organization_id
                                            ? ` · org ${assignment.organization_id.slice(0, 8)}`
                                            : ""}
                                        {assignment.project_id
                                            ? ` · project ${assignment.project_id.slice(0, 8)}`
                                            : ""}
                                    </Typography>
                                ))}
                            </Stack>
                        )}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Close</Button>
            </DialogActions>
        </Dialog>
    );
}

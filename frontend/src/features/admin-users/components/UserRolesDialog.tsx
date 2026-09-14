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
    type AdminUser,
} from "../../../api/admin";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

type Props = {
    user: AdminUser | null;
    open: boolean;
    onClose: () => void;
};

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
        mutationFn: () =>
            assignPolicyRole({
                user_id: userId,
                role_key: "system_admin",
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
        mutationFn: () =>
            revokePolicyRole({
                user_id: userId,
                role_key: "system_admin",
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({
                queryKey: queryKeys.admin.userRoleAssignments(userId),
            });
            await queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
        },
        onError: (error) => toastMutationError(error, "Failed to revoke role."),
    });

    const hasSystemAdmin = (assignmentsQuery.data ?? []).some(
        (assignment) => assignment.role_key === "system_admin"
    );
    const systemRole = (rolesQuery.data ?? []).find((role) => role.key === "system_admin");

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
                            Assign platform capabilities through roles. Organization membership still
                            grants org-scoped defaults automatically.
                        </Typography>
                        <Box
                            sx={(theme) => ({
                                p: 2,
                                borderRadius: 2,
                                border: `1px solid ${theme.palette.divider}`,
                            })}
                        >
                            <Typography variant="subtitle2">
                                {systemRole?.name ?? "System admin"}
                            </Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                                {systemRole?.description ?? "Full platform capability."}
                            </Typography>
                            <Button
                                size="small"
                                variant={hasSystemAdmin ? "outlined" : "contained"}
                                color={hasSystemAdmin ? "warning" : "primary"}
                                disabled={assignMutation.isPending || revokeMutation.isPending}
                                onClick={() =>
                                    hasSystemAdmin
                                        ? revokeMutation.mutate()
                                        : assignMutation.mutate()
                                }
                            >
                                {hasSystemAdmin ? "Revoke system admin" : "Grant system admin"}
                            </Button>
                        </Box>
                        {(assignmentsQuery.data ?? []).length > 0 && (
                            <Stack spacing={0.5}>
                                <Typography variant="caption" color="text.secondary">
                                    Current assignments
                                </Typography>
                                {(assignmentsQuery.data ?? []).map((assignment) => (
                                    <Typography key={assignment.id} variant="body2">
                                        {assignment.role_name} ({assignment.scope_type})
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

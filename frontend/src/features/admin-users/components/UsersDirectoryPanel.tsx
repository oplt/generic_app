import {
    Box,
    Button,
    Chip,
    CircularProgress,
    InputAdornment,
    Skeleton,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TablePagination,
    TableRow,
    TextField,
    Tooltip,
    Typography,
    useMediaQuery,
} from "@mui/material";
import { PeopleAlt as PeopleAltIcon, Search as SearchIcon } from "@mui/icons-material";
import { useTheme } from "@mui/material/styles";
import type { AdminUser } from "../../../api/admin";
import { EmptyState } from "../../../components/ui/EmptyState";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";
import { StatCard } from "../../../components/ui/StatCard";
import { formatDate } from "../../../utils/formatters";
import type { AdminUsersModel } from "../hooks/useAdminUsers";

type UsersDirectoryPanelProps = {
    m: AdminUsersModel;
};

function RoleChips({ roles }: { roles: string[] }) {
    return (
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {roles.map((role) => (
                <Chip key={role} label={role} size="small" />
            ))}
        </Stack>
    );
}

function ActiveSwitch({
    user,
    pending,
    onToggle,
}: {
    user: AdminUser;
    pending: boolean;
    onToggle: (isActive: boolean) => void;
}) {
    return (
        <Tooltip title={user.is_active ? "Deactivate" : "Activate"}>
            <Box component="span">
                {pending ? (
                    <CircularProgress size={18} />
                ) : (
                    <Switch
                        checked={user.is_active}
                        size="small"
                        inputProps={{
                            "aria-label": `${user.is_active ? "Deactivate" : "Activate"} ${user.full_name ?? user.email}`,
                        }}
                        onChange={(event) => onToggle(event.target.checked)}
                    />
                )}
            </Box>
        </Tooltip>
    );
}

export function UsersDirectoryPanel({ m }: UsersDirectoryPanelProps) {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    const { usersQuery, statusMutation, users } = m;

    return (
        <>
            <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
                <TextField
                    size="small"
                    placeholder="Search users..."
                    value={m.search}
                    onChange={(event) => m.updateSearch(event.target.value)}
                    InputProps={{
                        startAdornment: (
                            <InputAdornment position="start">
                                <SearchIcon fontSize="small" />
                            </InputAdornment>
                        ),
                    }}
                    sx={{ width: { xs: "100%", sm: 320 } }}
                />
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <StatCard
                    label="Total users"
                    value={m.total}
                    description="Matching current search"
                    icon={<PeopleAltIcon />}
                    loading={usersQuery.isLoading}
                />
                <StatCard
                    label="Active on page"
                    value={m.activeCount}
                    description="Allowed to access the product"
                    icon={<PeopleAltIcon />}
                    loading={usersQuery.isLoading}
                    color="success"
                />
                <StatCard
                    label="Verified on page"
                    value={m.verifiedCount}
                    description="Confirmed email identity"
                    icon={<PeopleAltIcon />}
                    loading={usersQuery.isLoading}
                    color="secondary"
                />
            </Box>

            <SectionCard title="User directory">
                <QueryBoundary
                    isLoading={usersQuery.isLoading}
                    isError={usersQuery.isError}
                    error={usersQuery.error}
                    errorFallback="Failed to load users."
                    onRetry={() => void usersQuery.refetch()}
                    loadingFallback={
                        <Stack spacing={1.5}>
                            {Array.from({ length: 5 }).map((_, index) => (
                                <Skeleton
                                    key={index}
                                    variant="rounded"
                                    height={88}
                                    sx={{ borderRadius: 4 }}
                                />
                            ))}
                        </Stack>
                    }
                    isEmpty={users.length === 0}
                    emptyFallback={
                        <EmptyState
                            icon={<PeopleAltIcon />}
                            title="No users found"
                            description="Try broadening the search or check if filters are too narrow."
                        />
                    }
                >
                    {isMobile ? (
                        <Stack spacing={1.5}>
                            {users.map((user) => {
                                const pending =
                                    statusMutation.isPending &&
                                    statusMutation.variables?.id === user.id;
                                return (
                                    <Box
                                        key={user.id}
                                        sx={(currentTheme) => ({
                                            p: 2.25,
                                            borderRadius: 4,
                                            border: `1px solid ${currentTheme.palette.divider}`,
                                        })}
                                    >
                                        <Stack spacing={1.25}>
                                            <Stack
                                                direction="row"
                                                justifyContent="space-between"
                                                spacing={1}
                                            >
                                                <Box sx={{ minWidth: 0 }}>
                                                    <Typography variant="subtitle2" noWrap>
                                                        {user.full_name ?? "Unnamed user"}
                                                    </Typography>
                                                    <Typography
                                                        variant="body2"
                                                        color="text.secondary"
                                                        noWrap
                                                    >
                                                        {user.email}
                                                    </Typography>
                                                </Box>
                                                <ActiveSwitch
                                                    user={user}
                                                    pending={Boolean(pending)}
                                                    onToggle={(is_active) =>
                                                        statusMutation.mutate({
                                                            id: user.id,
                                                            is_active,
                                                        })
                                                    }
                                                />
                                            </Stack>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                <RoleChips roles={user.roles} />
                                                <Chip
                                                    label={user.is_verified ? "Verified" : "Unverified"}
                                                    size="small"
                                                    color={user.is_verified ? "success" : "warning"}
                                                    variant="outlined"
                                                />
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary">
                                                Joined {formatDate(user.created_at)}
                                            </Typography>
                                            <Button size="small" onClick={() => m.setRolesUser(user)}>
                                                Manage roles
                                            </Button>
                                        </Stack>
                                    </Box>
                                );
                            })}
                        </Stack>
                    ) : (
                        <TableContainer>
                            <Table size="small" stickyHeader>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Email</TableCell>
                                        <TableCell>Name</TableCell>
                                        <TableCell>Roles</TableCell>
                                        <TableCell>Verified</TableCell>
                                        <TableCell>Joined</TableCell>
                                        <TableCell align="center">Active</TableCell>
                                        <TableCell align="right">Policy</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {users.map((user) => {
                                        const pending =
                                            statusMutation.isPending &&
                                            statusMutation.variables?.id === user.id;
                                        return (
                                            <TableRow key={user.id} hover>
                                                <TableCell>{user.email}</TableCell>
                                                <TableCell>{user.full_name ?? "—"}</TableCell>
                                                <TableCell>
                                                    <RoleChips roles={user.roles} />
                                                </TableCell>
                                                <TableCell>
                                                    <Chip
                                                        label={
                                                            user.is_verified ? "Verified" : "Unverified"
                                                        }
                                                        size="small"
                                                        color={
                                                            user.is_verified ? "success" : "warning"
                                                        }
                                                        variant="outlined"
                                                    />
                                                </TableCell>
                                                <TableCell>{formatDate(user.created_at)}</TableCell>
                                                <TableCell align="center">
                                                    <ActiveSwitch
                                                        user={user}
                                                        pending={Boolean(pending)}
                                                        onToggle={(is_active) =>
                                                            statusMutation.mutate({
                                                                id: user.id,
                                                                is_active,
                                                            })
                                                        }
                                                    />
                                                </TableCell>
                                                <TableCell align="right">
                                                    <Button
                                                        size="small"
                                                        onClick={() => m.setRolesUser(user)}
                                                    >
                                                        Roles
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    )}
                </QueryBoundary>

                <TablePagination
                    component="div"
                    count={m.total}
                    page={m.page}
                    rowsPerPage={m.pageSize}
                    rowsPerPageOptions={[m.pageSize]}
                    onPageChange={(_, nextPage) => m.setPage(nextPage)}
                />
            </SectionCard>
        </>
    );
}

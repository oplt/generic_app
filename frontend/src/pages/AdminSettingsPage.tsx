import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    IconButton,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { DeleteOutline as DeleteIcon, Storage as StorageIcon } from "@mui/icons-material";
import {
    createDatabaseSetting,
    deleteDatabaseSetting,
    getConfigSettings,
    listDatabaseSettings,
    updateConfigSettings,
    updateDatabaseSetting,
    type ConfigSettingsResponse,
    type DatabaseSetting,
} from "../api/settings";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { formatDateTime } from "../utils/formatters";

type DatabaseSettingDrafts = Record<
    string,
    {
        value: string;
        description: string;
    }
>;

function AdminSettingsContent({
    configData,
    databaseSettings,
    configErrorMessage,
    databaseErrorMessage,
    hasConfigError,
    hasDatabaseError,
}: {
    configData: ConfigSettingsResponse;
    databaseSettings: DatabaseSetting[];
    configErrorMessage: string;
    databaseErrorMessage: string;
    hasConfigError: boolean;
    hasDatabaseError: boolean;
}) {
    const queryClient = useQueryClient();
    const [configDrafts, setConfigDrafts] = useState<Record<string, string>>(() =>
        Object.fromEntries(configData.items.map((item) => [item.key, item.value]))
    );
    const [databaseDrafts, setDatabaseDrafts] = useState<DatabaseSettingDrafts>(() =>
        Object.fromEntries(
            databaseSettings.map((item) => [
                item.id,
                {
                    value: item.value,
                    description: item.description ?? "",
                },
            ])
        )
    );
    const [newSetting, setNewSetting] = useState({
        key: "",
        value: "",
        description: "",
    });

    const configMutation = useMutation({
        mutationFn: updateConfigSettings,
        onSuccess: (data) => {
            queryClient.setQueryData(["settings", "config"], data);
            setConfigDrafts(Object.fromEntries(data.items.map((item) => [item.key, item.value])));
        },
    });
    const createDatabaseMutation = useMutation({
        mutationFn: createDatabaseSetting,
        onSuccess: async () => {
            setNewSetting({ key: "", value: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const updateDatabaseMutation = useMutation({
        mutationFn: ({ id, value, description }: { id: string; value: string; description: string }) =>
            updateDatabaseSetting(id, { value, description }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const deleteDatabaseMutation = useMutation({
        mutationFn: deleteDatabaseSetting,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Administration"
                title="Settings"
                description="Manage environment-backed config and database settings from a calmer operational workspace with clearer grouping and feedback."
                meta={
                    <>
                        <Chip label={`${configData.items.length} config entries`} variant="outlined" />
                        <Chip label={`${databaseSettings.length} database settings`} variant="outlined" />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <StatCard
                    label="Config values"
                    value={configData.items.length}
                    description="Environment or file-backed product settings"
                    icon={<StorageIcon />}
                />
                <StatCard
                    label="Custom entries"
                    value={configData.items.filter((item) => item.is_custom).length}
                    description="Config values added outside the base template"
                    icon={<StorageIcon />}
                    color="secondary"
                />
                <StatCard
                    label="Database settings"
                    value={databaseSettings.length}
                    description="Runtime settings stored directly in the database"
                    icon={<StorageIcon />}
                    color="success"
                />
            </Box>

            {hasConfigError && <Alert severity="error">{configErrorMessage}</Alert>}
            {hasDatabaseError && <Alert severity="error">{databaseErrorMessage}</Alert>}

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.1fr) minmax(320px, 0.9fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard title="Config file" description="These values are written to `backend/.env`.">
                    <Stack spacing={2}>
                        <Alert severity="info">{configData.notice}</Alert>
                        {configMutation.isSuccess && (
                            <Alert severity="success">
                                Config saved. Restart the backend if a startup-bound value changed.
                            </Alert>
                        )}
                        {configMutation.isError && (
                            <Alert severity="error">
                                {configMutation.error instanceof Error
                                    ? configMutation.error.message
                                    : "Failed to save config."}
                            </Alert>
                        )}

                        <Stack spacing={1.5}>
                            {configData.items.map((item) => (
                                <Box
                                    key={item.key}
                                    sx={(theme) => ({
                                        p: 2,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1.25}>
                                        <Stack
                                            direction={{ xs: "column", sm: "row" }}
                                            justifyContent="space-between"
                                            spacing={1}
                                        >
                                            <Box>
                                                <Typography variant="subtitle2">{item.key}</Typography>
                                                {item.description && (
                                                    <Typography variant="body2" color="text.secondary">
                                                        {item.description}
                                                    </Typography>
                                                )}
                                            </Box>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                <Chip label={item.value_type} size="small" variant="outlined" />
                                                {item.is_custom && <Chip label="custom" size="small" variant="outlined" />}
                                                {item.requires_restart && (
                                                    <Chip label="restart recommended" size="small" color="warning" variant="outlined" />
                                                )}
                                            </Stack>
                                        </Stack>
                                        <TextField
                                            value={configDrafts[item.key] ?? item.value}
                                            onChange={(event) =>
                                                setConfigDrafts((current) => ({
                                                    ...current,
                                                    [item.key]: event.target.value,
                                                }))
                                            }
                                            fullWidth
                                        />
                                    </Stack>
                                </Box>
                            ))}
                        </Stack>

                        <Box>
                            <Button
                                variant="contained"
                                disabled={configMutation.isPending}
                                onClick={() =>
                                    configMutation.mutate({
                                        items: configData.items.map((item) => ({
                                            key: item.key,
                                            value: configDrafts[item.key] ?? "",
                                        })),
                                    })
                                }
                            >
                                {configMutation.isPending ? "Saving..." : "Save config"}
                            </Button>
                        </Box>
                    </Stack>
                </SectionCard>

                <SectionCard title="Add database setting" description="Store arbitrary key/value settings inside the database.">
                    <Stack spacing={2}>
                        {createDatabaseMutation.isSuccess && (
                            <Alert severity="success">Database setting created.</Alert>
                        )}
                        {createDatabaseMutation.isError && (
                            <Alert severity="error">
                                {createDatabaseMutation.error instanceof Error
                                    ? createDatabaseMutation.error.message
                                    : "Failed to create database setting."}
                            </Alert>
                        )}
                        <TextField
                            label="Key"
                            value={newSetting.key}
                            onChange={(event) =>
                                setNewSetting((current) => ({ ...current, key: event.target.value }))
                            }
                            fullWidth
                        />
                        <TextField
                            label="Value"
                            value={newSetting.value}
                            onChange={(event) =>
                                setNewSetting((current) => ({ ...current, value: event.target.value }))
                            }
                            fullWidth
                            multiline
                            minRows={3}
                        />
                        <TextField
                            label="Description"
                            value={newSetting.description}
                            onChange={(event) =>
                                setNewSetting((current) => ({ ...current, description: event.target.value }))
                            }
                            fullWidth
                            multiline
                            minRows={3}
                        />
                        <Button
                            variant="contained"
                            disabled={createDatabaseMutation.isPending || !newSetting.key.trim()}
                            onClick={() =>
                                createDatabaseMutation.mutate({
                                    key: newSetting.key.trim(),
                                    value: newSetting.value,
                                    description: newSetting.description || undefined,
                                })
                            }
                        >
                            {createDatabaseMutation.isPending ? "Adding..." : "Add setting"}
                        </Button>
                    </Stack>
                </SectionCard>
            </Box>

            <SectionCard title="Database settings" description="Review, edit, and delete runtime settings stored in the database.">
                {databaseSettings.length > 0 ? (
                    <Stack spacing={1.5}>
                        {databaseSettings.map((item) => {
                            const isSavingThisItem =
                                updateDatabaseMutation.isPending &&
                                updateDatabaseMutation.variables?.id === item.id;
                            const isDeletingThisItem =
                                deleteDatabaseMutation.isPending &&
                                deleteDatabaseMutation.variables === item.id;

                            return (
                                <Box
                                    key={item.id}
                                    sx={(theme) => ({
                                        p: 2.25,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1.5}>
                                        <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                                            <Box>
                                                <Typography variant="subtitle2">{item.key}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    Updated {formatDateTime(item.updated_at)}
                                                </Typography>
                                            </Box>
                                            <IconButton
                                                color="error"
                                                onClick={() => deleteDatabaseMutation.mutate(item.id)}
                                                disabled={isDeletingThisItem}
                                            >
                                                <DeleteIcon />
                                            </IconButton>
                                        </Stack>
                                        <TextField
                                            label="Value"
                                            value={databaseDrafts[item.id]?.value ?? item.value}
                                            onChange={(event) =>
                                                setDatabaseDrafts((current) => ({
                                                    ...current,
                                                    [item.id]: {
                                                        value: event.target.value,
                                                        description: current[item.id]?.description ?? item.description ?? "",
                                                    },
                                                }))
                                            }
                                            fullWidth
                                            multiline
                                            minRows={3}
                                        />
                                        <TextField
                                            label="Description"
                                            value={databaseDrafts[item.id]?.description ?? item.description ?? ""}
                                            onChange={(event) =>
                                                setDatabaseDrafts((current) => ({
                                                    ...current,
                                                    [item.id]: {
                                                        value: current[item.id]?.value ?? item.value,
                                                        description: event.target.value,
                                                    },
                                                }))
                                            }
                                            fullWidth
                                            multiline
                                            minRows={3}
                                        />
                                        <Button
                                            variant="contained"
                                            disabled={isSavingThisItem}
                                            onClick={() =>
                                                updateDatabaseMutation.mutate({
                                                    id: item.id,
                                                    value: databaseDrafts[item.id]?.value ?? item.value,
                                                    description: databaseDrafts[item.id]?.description ?? item.description ?? "",
                                                })
                                            }
                                        >
                                            {isSavingThisItem ? "Saving..." : "Save setting"}
                                        </Button>
                                    </Stack>
                                </Box>
                            );
                        })}
                    </Stack>
                ) : (
                    <EmptyState
                        icon={<StorageIcon />}
                        title="No database settings yet"
                        description="Create a setting above when you need runtime-configurable values stored in the database."
                    />
                )}
            </SectionCard>
        </PageShell>
    );
}

export default function AdminSettingsPage() {
    const {
        data: configData,
        isLoading: configLoading,
        error: configError,
    } = useQuery({
        queryKey: ["settings", "config"],
        queryFn: getConfigSettings,
    });
    const {
        data: databaseSettings,
        isLoading: databaseLoading,
        error: databaseError,
    } = useQuery({
        queryKey: ["settings", "database"],
        queryFn: listDatabaseSettings,
    });

    if ((configLoading && !configData) || (databaseLoading && !databaseSettings)) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={320} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!configData || !databaseSettings) {
        return null;
    }

    const settingsKey = `${configData.items.map((item) => `${item.key}:${item.value}`).join("|")}::${databaseSettings
        .map((item) => `${item.id}:${item.updated_at}`)
        .join("|")}`;

    return (
        <AdminSettingsContent
            key={settingsKey}
            configData={configData}
            databaseSettings={databaseSettings}
            configErrorMessage={
                configError instanceof Error ? configError.message : "Failed to load config values."
            }
            databaseErrorMessage={
                databaseError instanceof Error ? databaseError.message : "Failed to load database settings."
            }
            hasConfigError={Boolean(configError)}
            hasDatabaseError={Boolean(databaseError)}
        />
    );
}

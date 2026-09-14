import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    CircularProgress,
    Stack,
    Typography,
} from "@mui/material";
import { Psychology as MemoryIcon } from "@mui/icons-material";
import { useState } from "react";
import { deleteMyMemory, listMyMemories, type MemoryItem } from "../../../api/memory";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import { SectionTitleWithHelp } from "../../../components/ui/SectionTitleWithHelp";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";
import { usePlatformMetadata } from "../../../hooks/usePlatformMetadata";
import { formatDate } from "../../../utils/formatters";

const PAGE_SIZE = 20;

/** Compact personal-memory privacy controls for Profile. */
export function ProfileMemorySection() {
    const queryClient = useQueryClient();
    const toastMutationError = useMutationErrorToast();
    const { data: platform } = usePlatformMetadata();
    const memoryActive = (platform?.active_modules ?? []).includes("memory");
    const [pendingDelete, setPendingDelete] = useState<MemoryItem | null>(null);

    const listQuery = useQuery({
        queryKey: queryKeys.memory.list(PAGE_SIZE, 0),
        queryFn: () => listMyMemories({ limit: PAGE_SIZE, offset: 0 }),
        enabled: memoryActive,
        retry: false,
    });

    const deleteMutation = useMutation({
        mutationFn: (memoryId: string) => deleteMyMemory(memoryId),
        onSuccess: async () => {
            setPendingDelete(null);
            await queryClient.invalidateQueries({ queryKey: queryKeys.memory.all });
        },
        onError: (error) => toastMutationError(error, "Failed to delete memory."),
    });

    if (!memoryActive) {
        return null;
    }

    const items = listQuery.data?.items ?? [];

    return (
        <>
            <SectionCard
                title={
                    <SectionTitleWithHelp
                        title="Personal memory"
                        help="Memories the assistant may recall about you. Delete anything you do not want kept. Embedding/vector internals are never shown here."
                    />
                }
            >
                {listQuery.isLoading ? (
                    <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                        <CircularProgress size={28} />
                    </Box>
                ) : listQuery.isError ? (
                    <Typography variant="body2" color="text.secondary">
                        Memory is enabled for this profile but could not be loaded right now.
                    </Typography>
                ) : items.length === 0 ? (
                    <EmptyState
                        icon={<MemoryIcon />}
                        title="No saved memories"
                        description="Nothing stored for your account yet."
                    />
                ) : (
                    <Stack spacing={1.5}>
                        {items.map((item) => (
                            <Box
                                key={item.id}
                                sx={(theme) => ({
                                    p: 1.75,
                                    borderRadius: 2,
                                    border: `1px solid ${theme.palette.divider}`,
                                })}
                            >
                                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                                    {item.content}
                                </Typography>
                                <Stack
                                    direction="row"
                                    spacing={1}
                                    alignItems="center"
                                    justifyContent="space-between"
                                    sx={{ mt: 1 }}
                                >
                                    <Typography variant="caption" color="text.secondary">
                                        {item.metadata?.memory_type ?? "memory"}
                                        {item.metadata?.memory_level
                                            ? ` · ${item.metadata.memory_level}`
                                            : ""}
                                        {item.created_at ? ` · ${formatDate(item.created_at)}` : ""}
                                    </Typography>
                                    <Button
                                        size="small"
                                        color="warning"
                                        disabled={deleteMutation.isPending}
                                        onClick={() => setPendingDelete(item)}
                                    >
                                        Delete
                                    </Button>
                                </Stack>
                            </Box>
                        ))}
                        {(listQuery.data?.total ?? 0) > items.length ? (
                            <Typography variant="caption" color="text.secondary">
                                Showing {items.length} of {listQuery.data?.total} memories.
                            </Typography>
                        ) : null}
                    </Stack>
                )}
            </SectionCard>

            <ConfirmDialog
                open={Boolean(pendingDelete)}
                title="Delete this memory?"
                description={
                    <Typography variant="body2">
                        Remove this personal memory permanently. The assistant will no longer
                        recall it.
                        {pendingDelete?.content ? (
                            <>
                                <br />
                                <br />
                                <em>
                                    {pendingDelete.content.length > 160
                                        ? `${pendingDelete.content.slice(0, 160)}…`
                                        : pendingDelete.content}
                                </em>
                            </>
                        ) : null}
                    </Typography>
                }
                confirmLabel="Delete"
                confirmColor="warning"
                pending={deleteMutation.isPending}
                onConfirm={() => {
                    if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
                }}
                onClose={() => setPendingDelete(null)}
            />
        </>
    );
}

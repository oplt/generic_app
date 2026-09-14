import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Stack,
    Typography,
} from "@mui/material";
import { Add as AddIcon } from "@mui/icons-material";
import { ApiError } from "../../../api/client";
import { PageShell } from "../../../components/ui/PageShell";
import { SectionCard } from "../../../components/ui/SectionCard";
import { queryKeys } from "../../../config/queryKeys";
import {
    createChatConversation,
    clearChatConversation,
    deleteChatConversation,
    updateChatConversation,
} from "../api";
import { ChatPanel } from "../components/ChatPanel";
import { DocumentPanel } from "../components/DocumentPanel";
import { ConversationList } from "../components/ConversationList";
import { useChatStream } from "../hooks/useChatStream";
import { useChatSelection } from "../hooks/useChatSelection";
import { useConversationList } from "../hooks/useConversationList";
import { useDocumentUpload } from "../hooks/useDocumentUpload";
import { useKnowledgeDocuments } from "../hooks/useKnowledgeDocuments";
import type { ChatMode } from "../types";

function errorText(error: unknown) {
    if (error instanceof ApiError && error.code === "feature_disabled") {
        return "Knowledge chat is not enabled yet. An administrator must enable CHAT_ENABLED before using it.";
    }
    if (error instanceof ApiError && (error.code === "search_unavailable" || error.code === "web_search_unavailable")) {
        return "Web search is temporarily unavailable. Try again later.";
    }
    if (error instanceof ApiError && (error.code === "documents_required" || error.code === "no_documents_selected")) {
        return "Select at least one indexed document first.";
    }
    return error instanceof Error ? error.message : "The knowledge chat request failed.";
}

export default function KnowledgeChatPage() {
    const queryClient = useQueryClient();
    const [draft, setDraft] = useState("");
    const [uiError, setUiError] = useState<string | null>(null);
    const documentsState = useKnowledgeDocuments();
    const uploadState = useDocumentUpload(undefined, documentsState.invalidate);
    const conversationsState = useConversationList();
    const activeConversationId = conversationsState.activeConversationId;
    const conversation = conversationsState.selectedConversation;
    const createMutation = useMutation({
        mutationFn: (input: { mode: ChatMode; selectedDocumentIds: string[]; memoryEnabled: boolean; memoryWriteEnabled: boolean }) =>
            createChatConversation(input.mode, input.selectedDocumentIds, undefined, input.memoryEnabled, input.memoryWriteEnabled),
        onSuccess: (conversation) => {
            conversationsState.selectConversation(conversation.id);
            queryClient.setQueryData(queryKeys.chat.conversation(conversation.id), conversation);
            queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations });
        },
    });
    const deleteConversationMutation = useMutation({
        mutationFn: (id: string) => deleteChatConversation(id),
        onSuccess: (_, id) => {
            if (activeConversationId === id) conversationsState.selectConversation("");
            queryClient.removeQueries({ queryKey: queryKeys.chat.conversation(id) });
            queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations });
        },
    });
    const updateMutation = useMutation({
        mutationFn: (input: { id: string; selected_document_ids?: string[]; memory_enabled?: boolean; memory_write_enabled?: boolean }) =>
            updateChatConversation(input.id, {
                selected_document_ids: input.selected_document_ids,
                memory_enabled: input.memory_enabled,
                memory_write_enabled: input.memory_write_enabled,
        }),
        onSuccess: (updated) => {
            void queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversation(updated.id) });
            queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations });
        },
    });
    const clearMutation = useMutation({
        mutationFn: (id: string) => clearChatConversation(id),
        onSuccess: () => {
            if (activeConversationId) {
                queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversation(activeConversationId) });
            }
        },
    });

    const selection = useChatSelection({
        conversation,
        onPersist: (patch) => {
            if (activeConversationId) updateMutation.mutate({ id: activeConversationId, ...patch });
        },
    });

    const documents = useMemo(() => documentsState.documents, [documentsState.documents]);
    const displayedUploadProgress = useMemo(() => {
        if (!uploadState.progress?.job) return uploadState.progress;
        const refreshed = documentsState.jobs.find((job) => job.id === uploadState.progress?.job?.id);
        return refreshed ? { ...uploadState.progress, job: refreshed } : uploadState.progress;
    }, [documentsState.jobs, uploadState.progress]);
    const messages = conversation?.messages ?? [];
    const effectiveMode = conversation?.mode ?? selection.mode;
    const effectiveMemoryEnabled = conversation?.memory_enabled ?? selection.memoryEnabled;
    const effectiveMemoryWriteEnabled = conversation?.memory_write_enabled ?? selection.memoryWriteEnabled;
    const canSend = effectiveMode === "documents"
        ? selection.selectedDocumentIds.length > 0
        : true;
    const onStreamComplete = useCallback(async (id: string) => {
        await queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversation(id) });
        await queryClient.invalidateQueries({ queryKey: queryKeys.chat.conversations });
    }, [queryClient]);
    const onStreamError = useCallback((error: unknown) => setUiError(errorText(error)), []);
    const { streaming, send: sendStream, cancel: cancelStreaming } = useChatStream({
        onSettled: onStreamComplete,
        onError: onStreamError,
    });

    async function sendMessage() {
        const content = draft.trim();
        if (!content || streaming || !canSend) return;
        let targetId = activeConversationId;
        if (!targetId) {
            try {
                const created = await createMutation.mutateAsync({
                    mode: selection.mode,
                    selectedDocumentIds: selection.selectedDocumentIds,
                    memoryEnabled: selection.memoryEnabled,
                    memoryWriteEnabled: selection.memoryWriteEnabled,
                });
                targetId = created.id;
            } catch (error) {
                setUiError(errorText(error));
                return;
            }
        }
        setDraft("");
        await sendStream(targetId, {
            contract_version: "v1",
            content,
            mode: effectiveMode,
            document_ids: effectiveMode === "general" || effectiveMode === "web" ? [] : selection.selectedDocumentIds,
            memory_enabled: effectiveMemoryEnabled,
            memory_write_enabled: effectiveMemoryWriteEnabled,
        });
    }

    return (
        <PageShell>
            <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={2}>
                <Box>
                    <Typography variant="overline" color="text.secondary">Knowledge workspace</Typography>
                    <Typography variant="h3">Document chat</Typography>
                    <Typography color="text.secondary">Ask questions against indexed documents with evidence attached to every answer.</Typography>
                </Box>
                <Button variant="outlined" startIcon={<AddIcon />} onClick={() => { conversationsState.selectConversation(""); selection.reset(); }} disabled={Boolean(streaming)} sx={{ alignSelf: { sm: "center" } }}>
                    New chat
                </Button>
            </Stack>
            <Stack spacing={2}>
                {(documentsState.error || documentsState.mutationError || conversationsState.error || uploadState.error || uiError) && (
                    <Alert severity="error" onClose={() => { setUiError(null); uploadState.reset(); }}>{uiError ?? errorText(uploadState.error ?? documentsState.mutationError ?? documentsState.error ?? conversationsState.error)}</Alert>
                )}
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(260px, 0.34fr) minmax(0, 1fr)" }, gap: 2, alignItems: "start" }}>
                    <Stack spacing={2}>
                        <SectionCard title="Conversations" description="Your saved knowledge chat history.">
                            <ConversationList conversations={conversationsState.conversations} activeConversationId={activeConversationId} isLoading={conversationsState.isLoading} onSelect={conversationsState.selectConversation} onDelete={(id) => deleteConversationMutation.mutate(id)} />
                        </SectionCard>
                        <SectionCard title="Evidence" description="Only indexed documents can be selected for strict document chat.">
                            <DocumentPanel
                                documents={documents}
                                selectedDocumentIds={selection.selectedDocumentIds}
                                isLoading={documentsState.isLoading}
                                isUploading={uploadState.isUploading}
                                uploadProgress={displayedUploadProgress}
                                jobs={documentsState.jobs}
                                retryPending={documentsState.retryPending}
                                onUploadFile={uploadState.upload}
                                onToggleDocument={selection.toggleDocument}
                                onReindex={documentsState.reindex}
                                reindexPending={documentsState.reindexPending}
                                onRetryJob={documentsState.retry}
                                onDelete={documentsState.remove}
                                deletePending={documentsState.removePending}
                            />
                        </SectionCard>
                    </Stack>
                    <ChatPanel
                        mode={selection.mode}
                        conversation={conversation}
                        messages={messages}
                        streaming={streaming}
                        draft={draft}
                        memoryEnabled={selection.memoryEnabled}
                        memoryWriteEnabled={selection.memoryWriteEnabled}
                        canSend={canSend}
                        onModeChange={selection.setMode}
                        onMemoryChange={selection.setMemory}
                        onDraftChange={setDraft}
                        onSend={() => void sendMessage()}
                        onCancel={cancelStreaming}
                        onClear={() => { if (activeConversationId) clearMutation.mutate(activeConversationId); }}
                        clearPending={clearMutation.isPending}
                    />
                </Box>
            </Stack>
        </PageShell>
    );
}


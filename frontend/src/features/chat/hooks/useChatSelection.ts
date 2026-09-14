import { useCallback, useMemo, useState } from "react";
import type { ChatConversation, ChatMode, RagDocument } from "../types";

type SelectionPatch = {
    selected_document_ids?: string[];
    memory_enabled?: boolean;
    memory_write_enabled?: boolean;
};

type SelectionState = {
    conversationId: string | null;
    selectedDocumentIds: string[];
    mode: ChatMode;
    memoryEnabled: boolean;
    memoryWriteEnabled: boolean;
};

type UseChatSelectionOptions = {
    conversation?: ChatConversation;
    onPersist?: (patch: SelectionPatch) => void;
};

const defaults: SelectionState = {
    conversationId: null,
    selectedDocumentIds: [],
    mode: "auto",
    memoryEnabled: true,
    memoryWriteEnabled: true,
};

export function useChatSelection({ conversation, onPersist }: UseChatSelectionOptions = {}) {
    const [local, setLocal] = useState<SelectionState | null>(null);
    const state = useMemo(() => conversation
        ? local?.conversationId === conversation.id
            ? local
            : {
                conversationId: conversation.id,
                selectedDocumentIds: conversation.selected_document_ids,
                mode: conversation.mode,
                memoryEnabled: conversation.memory_enabled,
                memoryWriteEnabled: conversation.memory_write_enabled,
            }
        : local?.conversationId === null ? local : defaults,
    [conversation, local]);

    const apply = useCallback((patch: Partial<SelectionState>, persisted?: SelectionPatch) => {
        setLocal({ ...state, ...patch });
        if (conversation && persisted) onPersist?.(persisted);
    }, [conversation, onPersist, state]);

    const toggleDocument = useCallback((document: RagDocument) => {
        if (document.status !== "indexed" || document.needs_reindex) return;
        const next = state.selectedDocumentIds.includes(document.id)
            ? state.selectedDocumentIds.filter((id) => id !== document.id)
            : [...state.selectedDocumentIds, document.id];
        apply({ selectedDocumentIds: next }, { selected_document_ids: next });
    }, [apply, state]);

    const setMemory = useCallback((kind: "read" | "write", checked: boolean) => {
        apply(
            kind === "read" ? { memoryEnabled: checked } : { memoryWriteEnabled: checked },
            kind === "read" ? { memory_enabled: checked } : { memory_write_enabled: checked },
        );
    }, [apply]);

    const reset = useCallback(() => setLocal(defaults), []);

    return {
        selectedDocumentIds: state.selectedDocumentIds,
        mode: state.mode,
        memoryEnabled: state.memoryEnabled,
        memoryWriteEnabled: state.memoryWriteEnabled,
        setMode: (next: ChatMode) => apply({ mode: next }),
        setMemory,
        toggleDocument,
        reset,
    };
}

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getChatConversation, listChatConversations } from "../api";
import { queryKeys } from "../../../config/queryKeys";

export function useConversationList() {
    const query = useQuery({
        queryKey: queryKeys.chat.conversations,
        queryFn: listChatConversations,
    });
    const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
    const activeId = selectedConversationId === ""
        ? null
        : selectedConversationId ?? query.data?.[0]?.id ?? null;
    const selectedQuery = useQuery({
        queryKey: activeId ? queryKeys.chat.conversation(activeId) : ["chat", "empty"],
        queryFn: () => getChatConversation(activeId as string),
        enabled: Boolean(activeId),
    });
    return {
        ...query,
        conversations: query.data ?? [],
        selectedConversationId,
        activeConversationId: activeId,
        selectConversation: setSelectedConversationId,
        selectedConversation: selectedQuery.data,
        selectedConversationQuery: selectedQuery,
    };
}

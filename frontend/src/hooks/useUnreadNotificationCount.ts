import { useQuery } from "@tanstack/react-query";

import { getUnreadCount } from "../api/notifications";
import { queryKeys } from "../config/queryKeys";
import { QUERY_STALE_TIMES } from "../config/queryTiming";

export function useUnreadNotificationCount() {
    return useQuery({
        queryKey: queryKeys.notifications.unreadCount,
        queryFn: ({ signal }) => getUnreadCount({ signal }),
        staleTime: QUERY_STALE_TIMES.notifications,
    });
}

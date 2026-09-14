import { memo } from "react";
import { Badge } from "@mui/material";
import { useUnreadNotificationCount } from "../../hooks/useUnreadNotificationCount";

type NotificationNavBadgeProps = {
    children: React.ReactNode;
};

function NotificationNavBadgeInner({ children }: NotificationNavBadgeProps) {
    const { data } = useUnreadNotificationCount();
    const unreadCount = data?.count ?? 0;

    if (unreadCount <= 0) {
        return <>{children}</>;
    }

    return (
        <Badge badgeContent={unreadCount} color="error">
            {children}
        </Badge>
    );
}

export const NotificationNavBadge = memo(NotificationNavBadgeInner);

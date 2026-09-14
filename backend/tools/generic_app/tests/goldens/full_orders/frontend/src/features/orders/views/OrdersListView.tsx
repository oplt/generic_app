import { Skeleton, Stack, Typography } from "@mui/material";

import { EmptyState } from "../../../components/ui/EmptyState";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";
import { useOrdersList } from "../hooks/useOrdersList";

export function OrdersListView() {
    const query = useOrdersList();
    const items = query.data ?? [];

    return (
        <PageShell title="Orders">
            <SectionCard
                title="Orders"
                description="Scaffolded list view from generic-app create-module."
            >
                <QueryBoundary
                    isLoading={query.isLoading}
                    isError={query.isError}
                    error={query.error}
                    isEmpty={!query.isLoading && items.length === 0}
                    errorFallback="Failed to load orders."
                    onRetry={() => void query.refetch()}
                    loadingFallback={<Skeleton variant="rounded" height={120} />}
                    emptyFallback={
                        <EmptyState
                            title="No orders yet"
                            description="Create the first item to populate this list."
                        />
                    }
                >
                    <Stack spacing={1.5}>
                        {items.map((item) => (
                            <Typography key={item.id} variant="body1">
                                {item.title}
                            </Typography>
                        ))}
                    </Stack>
                </QueryBoundary>
            </SectionCard>
        </PageShell>
    );
}

export default OrdersListView;

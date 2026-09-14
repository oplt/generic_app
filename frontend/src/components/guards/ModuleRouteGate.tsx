import { Navigate } from "react-router-dom";
import { Box, Skeleton, Stack } from "@mui/material";

import type { ModuleFrontendRoute } from "../../api/platform";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";

type ModuleRouteGateProps = {
    /** Manifest ``page_key`` that must be present in platform ``module_routes``. */
    pageKey: string;
    children: React.ReactNode;
    /** Optional module key fallback while older payloads omit module_routes. */
    moduleKey?: string;
};

function GateLoader() {
    return (
        <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
            <Stack spacing={2}>
                <Skeleton variant="rounded" height={120} />
                <Skeleton variant="rounded" height={240} />
            </Stack>
        </Box>
    );
}

/**
 * Gate a lazy route behind backend-provided module_routes / active_modules.
 * Inactive modules redirect to the dashboard instead of mounting feature data hooks.
 */
export function ModuleRouteGate({ pageKey, moduleKey, children }: ModuleRouteGateProps) {
    const { data, isLoading, isError } = usePlatformMetadata();

    if (isLoading) return <GateLoader />;
    if (isError || !data) return <Navigate to="/dashboard" replace />;

    const routes: ModuleFrontendRoute[] = data.module_routes ?? [];
    const byPageKey = routes.some((route) => route.page_key === pageKey);
    const byModule =
        moduleKey != null && (data.active_modules ?? []).includes(moduleKey);

    if (!byPageKey && !byModule) {
        return <Navigate to="/dashboard" replace />;
    }

    return <>{children}</>;
}

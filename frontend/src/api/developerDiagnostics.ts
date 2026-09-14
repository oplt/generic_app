import { apiFetch } from "./client";
import type { DeveloperRequestSummary } from "./developerDiagnosticsEvents";

export type {
    DeveloperRequestSummary,
} from "./developerDiagnosticsEvents";
export {
    DEVELOPER_DIAGNOSTICS_EVENT,
    DEVELOPER_DIAGNOSTICS_HEADER,
    parseDeveloperDiagnosticsHeader,
    publishDeveloperDiagnostics,
} from "./developerDiagnosticsEvents";

export type DeveloperDiagnosticsStatus = {
    enabled: boolean;
    environment: string;
    grafana_base_url: string | null;
    tempo_explore_url: string | null;
    note: string;
};

export type DeveloperDiagnosticsRecent = {
    enabled: boolean;
    items: DeveloperRequestSummary[];
};

export async function getDeveloperDiagnosticsStatus(): Promise<DeveloperDiagnosticsStatus> {
    return apiFetch("/developer/diagnostics/status");
}

export async function getDeveloperDiagnosticsRecent(
    limit = 20
): Promise<DeveloperDiagnosticsRecent> {
    return apiFetch(`/developer/diagnostics/recent?limit=${limit}`);
}

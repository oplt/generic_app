/**
 * Compatibility wrapper around generated Diagnostics OpenAPI clients.
 */
import { getDiagnosticsApiV1AdminDiagnosticsGet } from "../generated/endpoints/diagnostics/diagnostics";
import type {
    AiProviderDiagnostics,
    DiagnosticsResponse,
    DiagnosticsSection,
    DiagnosticsSectionState,
} from "../generated/models";

export type OperationalState = DiagnosticsSectionState;
export type { AiProviderDiagnostics, DiagnosticsSection };
export type DiagnosticsReport = DiagnosticsResponse;

export async function getDiagnostics(): Promise<DiagnosticsReport> {
    return getDiagnosticsApiV1AdminDiagnosticsGet();
}

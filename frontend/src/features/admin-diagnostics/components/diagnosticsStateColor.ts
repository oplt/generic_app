import type { OperationalState } from "../../../api/diagnostics";

export function diagnosticsStateColor(
    state: OperationalState
): "default" | "success" | "warning" | "error" | "info" {
    if (state === "healthy") return "success";
    if (state === "degraded") return "warning";
    if (state === "unavailable") return "error";
    if (state === "not_required") return "default";
    return "info";
}

/**
 * Orval custom fetch mutator.
 *
 * Routes generated OpenAPI calls through the shared cookie/CSRF-aware client
 * (`apiFetch`) so React Query hooks inherit refresh + error handling.
 */
import { API_BASE, apiFetch } from "./client";

const API_PREFIX = "/api/v1";

function toApiPath(url: string): string {
    if (url.startsWith(API_BASE)) {
        return url.slice(API_BASE.length) || "/";
    }
    try {
        if (url.startsWith("http://") || url.startsWith("https://")) {
            const parsed = new URL(url);
            url = parsed.pathname + parsed.search;
        }
    } catch {
        // keep url as-is
    }
    if (url.startsWith(API_PREFIX)) {
        return url.slice(API_PREFIX.length) || "/";
    }
    return url.startsWith("/") ? url : `/${url}`;
}

export const customFetch = async <T>(url: string, options?: RequestInit): Promise<T> => {
    return apiFetch<T>(toApiPath(url), options ?? {});
};

export default customFetch;

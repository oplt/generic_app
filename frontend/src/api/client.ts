import {
    parseDeveloperDiagnosticsHeader,
    publishDeveloperDiagnostics,
} from "./developerDiagnosticsEvents";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";
export const API_REQUEST_TIMEOUT_MS = 30_000;

let refreshPromise: Promise<boolean> | null = null;
let refreshPromiseGeneration: number | null = null;
let authSessionGeneration = 0;
let authSessionActive = true;

export const AUTH_SESSION_EXPIRED_EVENT = "generic-app:auth-session-expired";

export type ApiErrorOptions = {
    status?: number;
    code?: string;
    correlationId?: string;
    details?: unknown;
    fieldErrors?: Record<string, string[]>;
    retryAfterSeconds?: number;
    cancelled?: boolean;
    retryable?: boolean;
};

export class ApiError extends Error {
    readonly status: number;
    readonly code?: string;
    readonly correlationId?: string;
    readonly details?: unknown;
    readonly fieldErrors: Record<string, string[]>;
    readonly retryAfterSeconds?: number;
    readonly cancelled: boolean;
    readonly retryable: boolean;

    constructor(message: string, options: ApiErrorOptions = {}) {
        super(message);
        this.name = "ApiError";
        this.status = options.status ?? 0;
        this.code = options.code;
        this.correlationId = options.correlationId;
        this.details = options.details;
        this.fieldErrors = options.fieldErrors ?? {};
        this.retryAfterSeconds = options.retryAfterSeconds;
        this.cancelled = options.cancelled ?? false;
        this.retryable = options.retryable ?? false;
    }
}

function cancelledRequestError() {
    return new ApiError("The request was cancelled.", { cancelled: true });
}

function expireAuthSession(generation: number) {
    if (!authSessionActive || generation !== authSessionGeneration) return;
    authSessionActive = false;
    authSessionGeneration += 1;
    if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
    }
}

export function beginAuthLogout() {
    authSessionActive = false;
    authSessionGeneration += 1;
}

export function markAuthSessionActive() {
    authSessionActive = true;
    authSessionGeneration += 1;
}

function getFieldErrors(error: unknown): Record<string, string[]> {
    if (!error || typeof error !== "object") return {};
    const candidate = (error as { errors?: unknown }).errors;
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return {};

    return Object.fromEntries(
        Object.entries(candidate).map(([field, value]) => [
            field,
            Array.isArray(value) ? value.map(String) : [String(value)],
        ])
    );
}

function getErrorCode(error: unknown): string | undefined {
    if (!error || typeof error !== "object") return undefined;
    const value = error as { error_code?: unknown; code?: unknown; error?: { code?: unknown } };
    if (typeof value.error_code === "string") return value.error_code;
    if (typeof value.code === "string") return value.code;
    return typeof value.error?.code === "string" ? value.error.code : undefined;
}

function createRequestSignal(parentSignal?: AbortSignal | null) {
    const controller = new AbortController();
    let timedOut = false;
    const nativeTimeout = typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(API_REQUEST_TIMEOUT_MS)
        : null;
    const timeoutId = nativeTimeout
        ? undefined
        : globalThis.setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, API_REQUEST_TIMEOUT_MS);
    const abortOnTimeout = () => {
        timedOut = true;
        controller.abort();
    };
    nativeTimeout?.addEventListener("abort", abortOnTimeout, { once: true });
    const abortFromParent = () => controller.abort(parentSignal?.reason);
    if (parentSignal?.aborted) {
        controller.abort(parentSignal.reason);
    }
    parentSignal?.addEventListener("abort", abortFromParent, { once: true });

    return {
        signal: controller.signal,
        wasTimedOut: () => timedOut,
        cleanup: () => {
            if (timeoutId !== undefined) globalThis.clearTimeout(timeoutId);
            nativeTimeout?.removeEventListener("abort", abortOnTimeout);
            parentSignal?.removeEventListener("abort", abortFromParent);
        },
    };
}

function readCookie(name: string): string | null {
    const match = document.cookie.match(
        new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}=([^;]*)`)
    );
    return match ? decodeURIComponent(match[1]) : null;
}

async function refreshAccessToken(): Promise<boolean> {
    const requestSignal = createRequestSignal();
    try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            credentials: "include",
            headers: buildCsrfHeaders(),
            signal: requestSignal.signal,
        });
        return res.ok;
    } catch {
        return false;
    } finally {
        requestSignal.cleanup();
    }
}

function waitForRefresh(promise: Promise<boolean>, signal?: AbortSignal | null) {
    if (!signal) return promise;
    if (signal.aborted) return Promise.reject(cancelledRequestError());

    return new Promise<boolean>((resolve, reject) => {
        const abort = () => {
            signal.removeEventListener("abort", abort);
            reject(cancelledRequestError());
        };
        signal.addEventListener("abort", abort, { once: true });
        promise.then(
            (result) => {
                signal.removeEventListener("abort", abort);
                resolve(result);
            },
            (error) => {
                signal.removeEventListener("abort", abort);
                reject(error);
            },
        );
    });
}

async function refreshForRetry(signal?: AbortSignal | null): Promise<boolean> {
    if (signal?.aborted) throw cancelledRequestError();
    if (!authSessionActive) return false;

    if (!refreshPromise || refreshPromiseGeneration !== authSessionGeneration) {
        const generation = authSessionGeneration;
        const request = refreshAccessToken().then((refreshed) => {
            if (!refreshed) expireAuthSession(generation);
            return refreshed
                && authSessionActive
                && generation === authSessionGeneration;
        });
        refreshPromise = request;
        refreshPromiseGeneration = generation;
        void request.finally(() => {
            if (refreshPromise === request) {
                refreshPromise = null;
                refreshPromiseGeneration = null;
            }
        });
    }
    return waitForRefresh(refreshPromise, signal);
}

export function buildCsrfHeaders(): HeadersInit {
    const csrfToken = readCookie("csrf_token");
    return csrfToken ? { "X-CSRF-Token": csrfToken } : {};
}

export async function apiFetchStream(
    path: string,
    options: RequestInit = {},
    retry = true,
): Promise<Response> {
    const headers = new Headers(options.headers ?? {});
    if (!headers.has("X-CSRF-Token")) {
        const csrfValue = readCookie("csrf_token");
        if (csrfValue) headers.set("X-CSRF-Token", csrfValue);
    }

    let response: Response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...options,
            credentials: "include",
            headers,
        });
    } catch (error) {
        const cancelled = options.signal?.aborted ?? false;
        throw new ApiError(
            cancelled ? "The request was cancelled." : "The server could not be reached. Please try again.",
            { cancelled, retryable: !cancelled, details: error },
        );
    }

    if (response.status === 401 && retry && !options.signal?.aborted) {
        const refreshed = await refreshForRetry(options.signal);
        if (!refreshed) throw new ApiError("Session expired. Please sign in again.", { status: 401 });
        return apiFetchStream(path, options, false);
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        const detail = typeof error?.detail === "string" ? error.detail : "Request failed";
        throw new ApiError(detail, {
            status: response.status,
            code: getErrorCode(error),
            correlationId: response.headers.get("X-Correlation-ID") ?? undefined,
            details: error,
            retryable: response.status === 429 || response.status >= 500,
        });
    }
    return response;
}

export type UploadProgress = {
    loaded: number;
    total: number;
    percent: number;
};

export async function apiUpload<T>(
    path: string,
    body: FormData,
    options: {
        signal?: AbortSignal;
        onProgress?: (progress: UploadProgress) => void;
    } = {},
    retry = true,
): Promise<T> {
    return new Promise<T>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        let settled = false;
        const abort = () => xhr.abort();
        const cleanup = () => options.signal?.removeEventListener("abort", abort);
        const fail = (error: ApiError) => {
            if (settled) return;
            settled = true;
            cleanup();
            reject(error);
        };
        const finish = (value: T) => {
            if (settled) return;
            settled = true;
            cleanup();
            resolve(value);
        };

        xhr.open("POST", `${API_BASE}${path}`);
        xhr.withCredentials = true;
        xhr.timeout = 5 * 60 * 1000;
        const csrfToken = readCookie("csrf_token");
        if (csrfToken) xhr.setRequestHeader("X-CSRF-Token", csrfToken);
        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                options.onProgress?.({
                    loaded: event.loaded,
                    total: event.total,
                    percent: Math.round((event.loaded / event.total) * 100),
                });
            }
        };
        xhr.onload = () => {
            let payload: unknown = {};
            try {
                payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
            } catch {
                payload = {};
            }
            if (xhr.status === 401 && retry && !options.signal?.aborted) {
                void refreshForRetry(options.signal)
                    .then((refreshed) => {
                        if (!refreshed) {
                            fail(new ApiError("Session expired. Please sign in again.", { status: 401 }));
                            return;
                        }
                        void apiUpload<T>(path, body, options, false).then(finish, fail);
                    })
                    .catch((error) => {
                        fail(error instanceof ApiError ? error : new ApiError("Session refresh failed."));
                    });
                return;
            }
            if (xhr.status < 200 || xhr.status >= 300) {
                const error = payload as { detail?: unknown; errors?: unknown };
                const detail = typeof error.detail === "string" ? error.detail : "Upload failed";
                fail(new ApiError(detail, {
                    status: xhr.status,
                    code: getErrorCode(payload),
                    details: payload,
                    fieldErrors: getFieldErrors(payload),
                    retryable: xhr.status === 429 || xhr.status >= 500,
                }));
                return;
            }
            finish(payload as T);
        };
        xhr.onerror = () => fail(new ApiError("The server could not be reached. Please try again.", { retryable: true }));
        xhr.ontimeout = () => fail(new ApiError("The upload timed out. Please try again.", { retryable: true }));
        xhr.onabort = () => fail(new ApiError("The upload was cancelled.", { cancelled: true }));
        if (options.signal?.aborted) {
            abort();
            return;
        }
        options.signal?.addEventListener("abort", abort, { once: true });
        xhr.send(body);
    });
}

export type Paginated<T> = {
    items: T[];
    total: number | null;
    limit: number;
    offset: number;
    next_cursor?: string | null;
    has_more?: boolean;
};

export async function apiFetch<T>(
    path: string,
    options: RequestInit = {},
    retry = true
): Promise<T> {
    const headers = new Headers(options.headers ?? {});
    const isFormData = options.body instanceof FormData;

    if (!isFormData && options.body !== undefined && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    if (!headers.has("X-CSRF-Token")) {
        const csrfValue = readCookie("csrf_token");
        if (csrfValue) {
            headers.set("X-CSRF-Token", csrfValue);
        }
    }

    const requestSignal = createRequestSignal(options.signal);
    let response: Response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...options,
            headers,
            credentials: "include",
            signal: requestSignal.signal,
        });
    } catch (error) {
        requestSignal.cleanup();
        const cancelled = options.signal?.aborted ?? false;
        const timedOut = requestSignal.wasTimedOut();
        throw new ApiError(
            timedOut
                ? "The request timed out. Please try again."
                : cancelled
                    ? "The request was cancelled."
                    : "The server could not be reached. Please try again.",
            { retryable: !cancelled, cancelled, details: error }
        );
    }
    requestSignal.cleanup();

    const diagnosticsHeader = response.headers.get("X-Developer-Diagnostics");
    if (diagnosticsHeader) {
        const summary = parseDeveloperDiagnosticsHeader(diagnosticsHeader);
        if (summary) publishDeveloperDiagnostics(summary);
    }

    if (response.status === 401 && retry && !options.signal?.aborted) {
        const refreshed = await refreshForRetry(options.signal);
        if (!refreshed) {
            throw new ApiError("Session expired. Please sign in again.", { status: 401 });
        }
        if (options.signal?.aborted) {
            throw new ApiError("The request was cancelled.", { cancelled: true });
        }
        return apiFetch<T>(path, options, false);
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        const detail = typeof error?.detail === "string" ? error.detail : "Request failed";
        const fieldErrors = getFieldErrors(error);
        if (Array.isArray(error?.detail)) {
            for (const item of error.detail) {
                if (!item || typeof item !== "object") continue;
                const field = Array.isArray(item.loc) ? item.loc.at(-1) : undefined;
                if (typeof field === "string") {
                    fieldErrors[field] = [...(fieldErrors[field] ?? []), String(item.msg ?? "Invalid value")];
                }
            }
        }
        const retryAfter = response.headers.get("Retry-After");
        throw new ApiError(detail, {
            status: response.status,
            code: getErrorCode(error),
            correlationId: response.headers.get("X-Correlation-ID") ?? undefined,
            details: error,
            fieldErrors,
            retryAfterSeconds: retryAfter ? Number(retryAfter) || undefined : undefined,
            retryable: response.status === 429 || response.status >= 500,
        });
    }

    // Handle 204 No Content
    if (response.status === 204) return undefined as T;

    return response.json();
}

export async function apiFetchPage<T>(
    path: string,
    options: RequestInit = {}
): Promise<Paginated<T>> {
    return apiFetch<Paginated<T>>(path, options);
}

export async function apiFetchItems<T>(
    path: string,
    options: RequestInit = {}
): Promise<T[]> {
    const page = await apiFetchPage<T>(path, options);
    return page.items;
}

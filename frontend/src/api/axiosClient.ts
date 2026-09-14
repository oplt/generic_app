/**
 * Optional Axios instance aligned with cookie + CSRF auth.
 *
 * The generated Orval client uses `customFetch` by default (same stack as
 * `apiFetch`). Switch Orval `httpClient` to `axios` and point the mutator at
 * this module if you prefer Axios transport for generated calls.
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { API_BASE, buildCsrfHeaders } from "./client";

export const apiAxios = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
    headers: { "Content-Type": "application/json" },
});

apiAxios.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const csrf = buildCsrfHeaders() as Record<string, string>;
    for (const [key, value] of Object.entries(csrf)) {
        config.headers.set(key, value);
    }
    return config;
});

export function getAxiosErrorMessage(error: unknown, fallback = "Request failed"): string {
    const axiosError = error as AxiosError<{ detail?: string }>;
    if (typeof axiosError?.response?.data?.detail === "string") {
        return axiosError.response.data.detail;
    }
    if (axiosError?.message) return axiosError.message;
    return fallback;
}

export default apiAxios;

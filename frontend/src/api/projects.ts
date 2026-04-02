import { apiFetch } from "./client";

export async function listProjects() {
    return apiFetch<Array<{ id: string; name: string; description: string | null }>>(
        "/projects"
    );
}

export async function createProject(payload: {
    name: string;
    description?: string;
}) {
    return apiFetch<{ id: string; name: string; description: string | null }>(
        "/projects",
        {
            method: "POST",
            body: JSON.stringify(payload),
        }
    );
}
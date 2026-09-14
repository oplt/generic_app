import { apiFetch, apiFetchItems } from "./client";

export type Project = {
    id: string;
    organization_id: string;
    name: string;
    description: string | null;
    created_at: string;
};

export type ProjectSummary = { project_count: number; open_task_count: number };

export type ProjectTaskStatus = "backlog" | "todo" | "in_progress" | "review" | "done";
export type ProjectTaskPriority = "low" | "medium" | "high" | "urgent";

export type ProjectTaskAssignee = {
    id: string;
    email: string;
    full_name: string | null;
};

export type ProjectTask = {
    id: string;
    project_id: string;
    title: string;
    description: string | null;
    status: ProjectTaskStatus;
    priority: ProjectTaskPriority;
    due_date: string | null;
    position: number;
    assignee: ProjectTaskAssignee | null;
    created_at: string;
    updated_at: string;
};

export async function listProjects(options: RequestInit = {}): Promise<Project[]> {
    return apiFetchItems<Project>("/projects", options);
}

export async function getProjectSummary(options: RequestInit = {}): Promise<ProjectSummary> {
    return apiFetch("/projects/summary", options);
}

export async function getProject(projectId: string): Promise<Project> {
    return apiFetch(`/projects/${projectId}`);
}

export async function createProject(payload: {
    name: string;
    description?: string;
    organization_id?: string;
}): Promise<Project> {
    return apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function listProjectTasks(projectId: string): Promise<ProjectTask[]> {
    return apiFetchItems<ProjectTask>(`/projects/${projectId}/tasks`);
}

export async function createProjectTask(
    projectId: string,
    payload: {
        title: string;
        description?: string;
        status: ProjectTaskStatus;
        priority: ProjectTaskPriority;
        due_date?: string | null;
        assignee_id?: string | null;
    }
): Promise<ProjectTask> {
    return apiFetch(`/projects/${projectId}/tasks`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function updateProjectTask(
    projectId: string,
    taskId: string,
    payload: Partial<{
        title: string;
        description: string | null;
        status: ProjectTaskStatus;
        priority: ProjectTaskPriority;
        due_date: string | null;
        assignee_id: string | null;
    }>
): Promise<ProjectTask> {
    return apiFetch(`/projects/${projectId}/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function deleteProjectTask(projectId: string, taskId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/tasks/${taskId}`, {
        method: "DELETE",
    });
}

export async function reorderProjectTasks(
    projectId: string,
    payload: {
        columns: Array<{
            status: ProjectTaskStatus;
            task_ids: string[];
        }>;
    }
): Promise<ProjectTask[]> {
    return apiFetch(`/projects/${projectId}/tasks/reorder`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}

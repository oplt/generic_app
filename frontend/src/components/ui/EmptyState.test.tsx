import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
    it("renders title, description, and optional action", () => {
        render(
            <EmptyState
                title="No projects yet"
                description="Create a project to get started."
                action={<button type="button">Create project</button>}
            />
        );

        expect(screen.getByText("No projects yet")).toBeTruthy();
        expect(screen.getByText("Create a project to get started.")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Create project" })).toBeTruthy();
    });
});

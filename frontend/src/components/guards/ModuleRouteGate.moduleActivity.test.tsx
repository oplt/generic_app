import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../hooks/usePlatformMetadata", () => ({
    usePlatformMetadata: vi.fn(),
}));

import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { ModuleRouteGate } from "./ModuleRouteGate";

const mockedMeta = vi.mocked(usePlatformMetadata);

describe("ModuleRouteGate module activity", () => {
    beforeEach(() => {
        mockedMeta.mockReset();
    });

    it("shows not-found when page_key and moduleKey are both inactive", () => {
        mockedMeta.mockReturnValue({
            data: {
                module_routes: [{ page_key: "projects.list", path: "/projects" }],
                active_modules: ["projects"],
            },
            isLoading: false,
            isError: false,
        } as never);

        render(
            <MemoryRouter initialEntries={["/ai"]}>
                <Routes>
                    <Route
                        path="/ai"
                        element={
                            <ModuleRouteGate pageKey="ai.studio" moduleKey="ai">
                                <div>ai-studio</div>
                            </ModuleRouteGate>
                        }
                    />
                </Routes>
            </MemoryRouter>
        );

        expect(screen.getByText("Page not found")).toBeTruthy();
        expect(screen.queryByText("ai-studio")).toBeNull();
    });

    it("allows route when page_key is listed in module_routes", () => {
        mockedMeta.mockReturnValue({
            data: {
                module_routes: [{ page_key: "ai.studio", path: "/ai" }],
                active_modules: ["projects"],
            },
            isLoading: false,
            isError: false,
        } as never);

        render(
            <MemoryRouter initialEntries={["/ai"]}>
                <Routes>
                    <Route
                        path="/ai"
                        element={
                            <ModuleRouteGate pageKey="ai.studio" moduleKey="ai">
                                <div>ai-studio</div>
                            </ModuleRouteGate>
                        }
                    />
                </Routes>
            </MemoryRouter>
        );

        expect(screen.getByText("ai-studio")).toBeTruthy();
    });

    it("allows module via active_modules fallback when module_routes omit the page", () => {
        mockedMeta.mockReturnValue({
            data: {
                module_routes: [],
                active_modules: ["ai", "rag"],
            },
            isLoading: false,
            isError: false,
        } as never);

        render(
            <MemoryRouter initialEntries={["/ai"]}>
                <Routes>
                    <Route
                        path="/ai"
                        element={
                            <ModuleRouteGate pageKey="ai.studio" moduleKey="ai">
                                <div>ai-studio</div>
                            </ModuleRouteGate>
                        }
                    />
                </Routes>
            </MemoryRouter>
        );

        expect(screen.getByText("ai-studio")).toBeTruthy();
    });
});

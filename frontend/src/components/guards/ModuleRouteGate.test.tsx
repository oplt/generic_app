import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../hooks/usePlatformMetadata", () => ({
    usePlatformMetadata: vi.fn(),
}));

import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { ModuleRouteGate } from "./ModuleRouteGate";

const mockedMeta = vi.mocked(usePlatformMetadata);

function renderGate(pageKey: string, moduleKey?: string) {
    return render(
        <MemoryRouter initialEntries={["/feature"]}>
            <Routes>
                <Route
                    path="/feature"
                    element={
                        <ModuleRouteGate pageKey={pageKey} moduleKey={moduleKey}>
                            <div>feature-content</div>
                        </ModuleRouteGate>
                    }
                />
                <Route path="/dashboard" element={<div>dashboard</div>} />
            </Routes>
        </MemoryRouter>
    );
}

describe("ModuleRouteGate", () => {
    beforeEach(() => {
        mockedMeta.mockReset();
    });

    it("allows routes listed in platform module_routes", () => {
        mockedMeta.mockReturnValue({
            data: {
                module_routes: [{ page_key: "orders.list", path: "/orders" }],
                active_modules: [],
            },
            isLoading: false,
            isError: false,
        } as never);
        renderGate("orders.list");
        expect(screen.getByText("feature-content")).toBeTruthy();
    });

    it("redirects when the page is not in the active profile allow-list", () => {
        mockedMeta.mockReturnValue({
            data: {
                module_routes: [{ page_key: "projects.list", path: "/projects" }],
                active_modules: ["projects"],
            },
            isLoading: false,
            isError: false,
        } as never);
        renderGate("orders.list", "orders");
        expect(screen.getByText("dashboard")).toBeTruthy();
        expect(screen.queryByText("feature-content")).toBeNull();
    });
});

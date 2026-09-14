import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Box, Tab, Tabs } from "@mui/material";
import { useState } from "react";

function DemoTabs() {
    const [value, setValue] = useState("probe");
    return (
        <Box>
            <Tabs
                value={value}
                onChange={(_event, next) => setValue(next)}
                aria-label="Demo workflows"
            >
                <Tab id="probe-tab" value="probe" label="Probe" aria-controls="probe-panel" />
                <Tab id="runs-tab" value="runs" label="Runs" aria-controls="runs-panel" />
            </Tabs>
            <Box
                id={`${value}-panel`}
                role="tabpanel"
                aria-labelledby={`${value}-tab`}
            >
                {value === "probe" ? "probe-body" : "runs-body"}
            </Box>
        </Box>
    );
}

describe("task tabs keyboard accessibility", () => {
    it("activates tabs via click and exposes tablist semantics", async () => {
        const user = userEvent.setup();
        render(<DemoTabs />);

        expect(screen.getByRole("tablist", { name: "Demo workflows" })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: "Probe" })).toHaveAttribute("aria-selected", "true");
        expect(screen.getByText("probe-body")).toBeInTheDocument();

        await user.click(screen.getByRole("tab", { name: "Runs" }));
        expect(screen.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
        expect(screen.getByText("runs-body")).toBeInTheDocument();
    });
});

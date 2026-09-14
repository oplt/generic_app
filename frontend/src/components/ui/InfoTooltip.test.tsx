import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InfoTooltip } from "./InfoTooltip";

describe("InfoTooltip", () => {
    it("exposes an accessible help control", async () => {
        const user = userEvent.setup();
        render(<InfoTooltip title="Secondary help copy" label="About field" />);
        const button = screen.getByRole("button", { name: "About field" });
        expect(button).toBeInTheDocument();
        await user.hover(button);
        expect(await screen.findByText("Secondary help copy")).toBeInTheDocument();
    });
});

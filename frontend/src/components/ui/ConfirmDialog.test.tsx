import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog accessibility", () => {
    it("exposes dialog roles and keeps focusable confirm/cancel controls", async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();
        const onClose = vi.fn();

        render(
            <ConfirmDialog
                open
                title="Delete memory?"
                description="This removes the saved memory permanently."
                confirmLabel="Delete"
                confirmColor="warning"
                onConfirm={onConfirm}
                onClose={onClose}
            />
        );

        expect(screen.getByRole("dialog", { name: "Delete memory?" })).toBeInTheDocument();
        expect(screen.getByText("This removes the saved memory permanently.")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onClose).toHaveBeenCalledOnce();

        await user.click(screen.getByRole("button", { name: "Delete" }));
        expect(onConfirm).toHaveBeenCalledOnce();
    });

    it("disables actions while pending", () => {
        render(
            <ConfirmDialog
                open
                title="Working"
                description="Please wait"
                pending
                onConfirm={() => undefined}
                onClose={() => undefined}
            />
        );

        expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    });
});

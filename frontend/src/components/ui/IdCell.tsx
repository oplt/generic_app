import { useState } from "react";
import { IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { ContentCopy as CopyIcon } from "@mui/icons-material";

type IdCellProps = {
    id: string;
    /** Human-friendly primary label shown instead of the raw id. */
    label?: React.ReactNode;
    mono?: boolean;
};

/** Compact ID display: short label + tooltip/copy for full UUID. */
export function IdCell({ id, label, mono = true }: IdCellProps) {
    const [copied, setCopied] = useState(false);
    const short = id.length > 12 ? `${id.slice(0, 8)}…` : id;
    const primary = label ?? short;

    async function handleCopy(event: React.MouseEvent) {
        event.stopPropagation();
        try {
            await navigator.clipboard.writeText(id);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
        } catch {
            /* clipboard may be unavailable */
        }
    }

    return (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
            <Tooltip title={id}>
                <Typography
                    variant="body2"
                    noWrap
                    sx={{
                        fontFamily: mono ? "ui-monospace, monospace" : undefined,
                        maxWidth: 180,
                    }}
                >
                    {primary}
                </Typography>
            </Tooltip>
            <Tooltip title={copied ? "Copied" : "Copy ID"}>
                <IconButton size="small" aria-label={`Copy ID ${id}`} onClick={handleCopy}>
                    <CopyIcon fontSize="inherit" />
                </IconButton>
            </Tooltip>
        </Stack>
    );
}

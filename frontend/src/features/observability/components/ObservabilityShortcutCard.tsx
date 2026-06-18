import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { OpenInNew as OpenInNewIcon } from "@mui/icons-material";
import type { ReactNode } from "react";

type ObservabilityShortcutCardProps = {
    title: string;
    description: string;
    buttonText: string;
    url: string | null;
    allowed: boolean;
    configured: boolean;
    onOpen: (url: string) => void;
    icon: ReactNode;
};

export function ObservabilityShortcutCard({
    title,
    description,
    buttonText,
    url,
    allowed,
    configured,
    onOpen,
    icon,
}: ObservabilityShortcutCardProps) {
    const disabledReason = !allowed ? "Admin only" : !configured || !url ? "Not configured" : null;

    return (
        <Paper
            sx={{
                p: 2.5,
                borderRadius: 4,
                border: 1,
                borderColor: "divider",
                boxShadow: "none",
                minHeight: 218,
                display: "flex",
            }}
        >
            <Stack spacing={2} sx={{ width: "100%" }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1.5}>
                    <Typography variant="h6">{title}</Typography>
                    {icon}
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
                    {description}
                </Typography>
                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1.5}>
                    {disabledReason ? (
                        <Chip label={disabledReason} size="small" variant="outlined" />
                    ) : (
                        <span />
                    )}
                    <Button
                        variant="outlined"
                        endIcon={<OpenInNewIcon />}
                        disabled={Boolean(disabledReason) || !url}
                        onClick={() => {
                            if (url) {
                                onOpen(url);
                            }
                        }}
                    >
                        {buttonText}
                    </Button>
                </Stack>
            </Stack>
        </Paper>
    );
}

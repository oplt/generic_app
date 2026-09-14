import { IconButton, Link, Stack, Tooltip, Typography } from "@mui/material";
import { HelpOutline as HelpIcon } from "@mui/icons-material";

type InfoTooltipProps = {
    /** Short secondary explanation (not validation or danger). */
    title: React.ReactNode;
    label: string;
    learnMoreHref?: string;
    learnMoreLabel?: string;
    size?: "small" | "medium";
};

/**
 * Accessible secondary help: keyboard-focusable icon, touch-friendly Tooltip.
 * Never put validation errors, destructive warnings, or consent here.
 */
export function InfoTooltip({
    title,
    label,
    learnMoreHref,
    learnMoreLabel = "Learn more",
    size = "small",
}: InfoTooltipProps) {
    const content = learnMoreHref ? (
        <Stack spacing={0.5}>
            <Typography variant="body2" component="span">
                {title}
            </Typography>
            <Link href={learnMoreHref} target="_blank" rel="noopener noreferrer">
                {learnMoreLabel}
            </Link>
        </Stack>
    ) : (
        title
    );

    return (
        <Tooltip title={content} describeChild enterTouchDelay={0} leaveTouchDelay={3000}>
            <IconButton
                size={size}
                aria-label={label}
                sx={{ p: 0.5, color: "text.secondary" }}
            >
                <HelpIcon fontSize="inherit" />
            </IconButton>
        </Tooltip>
    );
}

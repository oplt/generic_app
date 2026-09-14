import { Stack, Typography } from "@mui/material";
import { InfoTooltip } from "./InfoTooltip";

type SectionTitleWithHelpProps = {
    title: string;
    help: React.ReactNode;
    helpLabel?: string;
    learnMoreHref?: string;
};

/** Concise section heading + adjacent help icon (replaces long permanent descriptions). */
export function SectionTitleWithHelp({
    title,
    help,
    helpLabel,
    learnMoreHref,
}: SectionTitleWithHelpProps) {
    return (
        <Stack direction="row" spacing={0.5} alignItems="center">
            <Typography component="span" variant="inherit">
                {title}
            </Typography>
            <InfoTooltip
                title={help}
                label={helpLabel ?? `About ${title}`}
                learnMoreHref={learnMoreHref}
            />
        </Stack>
    );
}

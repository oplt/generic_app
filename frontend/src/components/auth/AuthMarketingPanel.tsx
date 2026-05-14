import { Box, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type Highlight = {
    value: string;
    label: string;
};

type AuthMarketingPanelProps = {
    appName: string;
    eyebrow: string;
    title: string;
    description: string;
    highlights?: Highlight[];
    points?: string[];
};

export function AuthMarketingPanel({
    appName,
    eyebrow,
    title,
    description,
    highlights = [],
    points = [],
}: AuthMarketingPanelProps) {
    return (
        <Stack justifyContent="space-between" spacing={4} sx={{ height: "100%" }}>
            <Stack spacing={3}>
                <Box>
                    <Typography
                        variant="overline"
                        sx={(theme) => ({
                            color: alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.82 : 0.68),
                            display: "block",
                            mb: 1,
                        })}
                    >
                        {eyebrow}
                    </Typography>
                    <Typography variant="h3" sx={{ mb: 1.25 }}>
                        {title}
                    </Typography>
                    <Typography
                        sx={(theme) => ({
                            color: alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.78 : 0.7),
                            maxWidth: 620,
                        })}
                    >
                        {description}
                    </Typography>
                </Box>

                {highlights.length > 0 && (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.25,
                            gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" },
                        }}
                    >
                        {highlights.map((item) => (
                            <Box
                                key={item.label}
                                sx={(theme) => ({
                                    p: 2,
                                    borderRadius: 4,
                                    backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.12 : 0.58),
                                    border: `1px solid ${alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.14 : 0.08)}`,
                                })}
                            >
                                <Typography variant="h5">{item.value}</Typography>
                                <Typography
                                    sx={(theme) => ({
                                        color: alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.74 : 0.66),
                                        mt: 0.5,
                                    })}
                                >
                                    {item.label}
                                </Typography>
                            </Box>
                        ))}
                    </Box>
                )}
            </Stack>

            <Stack spacing={1.25}>
                <Typography
                    variant="subtitle2"
                    sx={(theme) => ({
                        color: alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.92 : 0.78),
                    })}
                >
                    {appName}
                </Typography>
                {points.map((point) => (
                    <Box
                        key={point}
                        sx={(theme) => ({
                            p: 1.5,
                            borderRadius: 3,
                            backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.08 : 0.45),
                            border: `1px solid ${alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.12 : 0.08)}`,
                        })}
                    >
                        <Typography
                            sx={(theme) => ({
                                color: alpha(theme.palette.text.primary, theme.palette.mode === "dark" ? 0.78 : 0.68),
                            })}
                        >
                            {point}
                        </Typography>
                    </Box>
                ))}
            </Stack>
        </Stack>
    );
}

import { Box, Chip, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type PageHeaderProps = {
    eyebrow?: string;
    title: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
    meta?: React.ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions, meta }: PageHeaderProps) {
    return (
        <Box
            sx={(theme) => ({
                position: "relative",
                overflow: "hidden",
                borderRadius: 6,
                border: `1px solid ${theme.palette.divider}`,
                px: { xs: 2.5, md: 4 },
                py: { xs: 3, md: 4 },
                backgroundColor: theme.palette.background.paper,
                boxShadow:
                    theme.palette.mode === "dark"
                        ? "0 18px 50px rgba(0, 0, 0, 0.28)"
                        : "0 4px 16px rgba(28, 25, 23, 0.04)",
                "&::before": {
                    content: '""',
                    position: "absolute",
                    width: { xs: 220, md: 340 },
                    height: { xs: 220, md: 340 },
                    right: { xs: -90, md: -80 },
                    top: { xs: -100, md: -130 },
                    borderRadius: "50%",
                    background: `radial-gradient(circle, ${alpha(theme.palette.secondary.main, 0.42)} 0%, ${alpha(
                        theme.palette.info.main,
                        0.18
                    )} 42%, transparent 70%)`,
                    filter: "blur(3px)",
                },
                "&::after": {
                    content: '""',
                    position: "absolute",
                    inset: 0,
                    backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.18 : 0.28),
                    pointerEvents: "none",
                },
            })}
        >
            <Stack
                direction={{ xs: "column", lg: actions ? "row" : "column" }}
                justifyContent="space-between"
                alignItems={{ xs: "flex-start", lg: "flex-end" }}
                spacing={3}
                sx={{ position: "relative", zIndex: 1 }}
            >
                <Box sx={{ maxWidth: 760 }}>
                    {eyebrow && (
                        <Chip
                            label={eyebrow}
                            size="small"
                            color="primary"
                            variant="outlined"
                            sx={{ mb: 1.5 }}
                        />
                    )}
                    <Typography variant="h3">{title}</Typography>
                    {description && (
                        <Typography
                            color="text.secondary"
                            sx={{ mt: 1.25, maxWidth: 720, fontSize: { xs: "0.95rem", md: "1.02rem" } }}
                        >
                            {description}
                        </Typography>
                    )}
                    {meta && (
                        <Stack direction="row" flexWrap="wrap" gap={1.25} sx={{ mt: 2.5 }}>
                            {meta}
                        </Stack>
                    )}
                </Box>
                {actions && (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} sx={{ width: { xs: "100%", lg: "auto" } }}>
                        {actions}
                    </Stack>
                )}
            </Stack>
        </Box>
    );
}

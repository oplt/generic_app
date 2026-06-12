import { Box, Paper, Skeleton, Stack, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";

type AccentColor = "primary" | "secondary" | "success" | "warning" | "error" | "info";

type StatCardProps = {
    label: string;
    value: React.ReactNode;
    description?: React.ReactNode;
    icon: React.ReactNode;
    loading?: boolean;
    color?: AccentColor;
};

export function StatCard({
    label,
    value,
    description,
    icon,
    loading = false,
    color = "primary",
}: StatCardProps) {
    const theme = useTheme();
    const accent = theme.palette[color].main;

    return (
        <Paper
            sx={{
                p: 2.5,
                borderRadius: 4,
                border: 1,
                borderColor: "divider",
                minHeight: "100%",
                backgroundColor: "background.paper",
                boxShadow: "none",
            }}
        >
            <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                    <Box>
                        <Typography variant="body2" color="text.secondary">
                            {label}
                        </Typography>
                    </Box>
                    <Box
                        sx={{
                            width: 44,
                            height: 44,
                            display: "grid",
                            placeItems: "center",
                            borderRadius: 4,
                            color: accent,
                            backgroundColor: alpha(accent, theme.palette.mode === "dark" ? 0.16 : 0.1),
                        }}
                    >
                        {icon}
                    </Box>
                </Stack>
                {loading ? (
                    <Stack spacing={0.75}>
                        <Skeleton variant="text" width={120} height={42} />
                        <Skeleton variant="text" width="70%" />
                    </Stack>
                ) : (
                    <Stack spacing={0.75}>
                        <Typography variant="h4">{value}</Typography>
                        {description && (
                            <Typography variant="body2" color="text.secondary">
                                {description}
                            </Typography>
                        )}
                    </Stack>
                )}
            </Stack>
        </Paper>
    );
}

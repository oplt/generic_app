import { Box, Container, Paper } from "@mui/material";
import { alpha } from "@mui/material/styles";

type AuthShellProps = {
    sideContent: React.ReactNode;
    children: React.ReactNode;
};

export function AuthShell({ sideContent, children }: AuthShellProps) {
    return (
        <Box
            sx={(theme) => ({
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                px: { xs: 2, md: 3 },
                py: { xs: 3, md: 4 },
                backgroundColor: theme.palette.background.default,
            })}
        >
            <Container maxWidth="xl" sx={{ px: "0 !important" }}>
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.08fr) minmax(420px, 0.92fr)" },
                        gap: { xs: 2.5, lg: 3 },
                        alignItems: "stretch",
                    }}
                >
                    <Paper
                        sx={(theme) => ({
                            p: { xs: 3, md: 4.5 },
                            borderRadius: 4,
                            overflow: "hidden",
                            position: "relative",
                            color: theme.palette.mode === "dark" ? "#ffffff" : "#0c0a09",
                            backgroundColor: theme.palette.background.paper,
                            backgroundImage:
                                theme.palette.mode === "dark"
                                    ? "radial-gradient(circle at 18% 18%, rgba(167, 229, 211, 0.22), transparent 34%), radial-gradient(circle at 86% 72%, rgba(200, 184, 224, 0.18), transparent 38%)"
                                    : "radial-gradient(circle at 18% 18%, rgba(167, 229, 211, 0.5), transparent 34%), radial-gradient(circle at 86% 72%, rgba(244, 197, 168, 0.36), transparent 38%)",
                            boxShadow:
                                theme.palette.mode === "dark"
                                    ? "0 18px 50px rgba(0, 0, 0, 0.3)"
                                    : "0 4px 16px rgba(28, 25, 23, 0.04)",
                            "&::after": {
                                content: '""',
                                position: "absolute",
                                inset: 0,
                                backgroundColor: alpha(theme.palette.background.paper, theme.palette.mode === "dark" ? 0.02 : 0.18),
                                pointerEvents: "none",
                            },
                        })}
                    >
                        <Box sx={{ position: "relative", zIndex: 1, height: "100%" }}>
                            {sideContent}
                        </Box>
                    </Paper>
                    <Paper
                        sx={{
                            p: { xs: 3, md: 4 },
                            borderRadius: 4,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            minHeight: { lg: 720 },
                        }}
                    >
                        <Box sx={{ width: "100%", maxWidth: 440 }}>{children}</Box>
                    </Paper>
                </Box>
            </Container>
        </Box>
    );
}

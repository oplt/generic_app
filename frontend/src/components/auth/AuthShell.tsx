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
                background: theme.palette.mode === "dark"
                    ? "linear-gradient(180deg, #0c0a09 0%, #1c1917 100%)"
                    : "linear-gradient(180deg, #f5f5f5 0%, #fafafa 100%)",
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
                            background:
                                theme.palette.mode === "dark"
                                    ? "linear-gradient(145deg, #292524 0%, #1c1917 62%, #0c0a09 100%)"
                                    : "linear-gradient(145deg, #ffffff 0%, #f0efed 56%, #dcebe6 100%)",
                            boxShadow:
                                theme.palette.mode === "dark"
                                    ? "0 24px 70px rgba(0, 0, 0, 0.48)"
                                    : "0 28px 70px rgba(41, 37, 36, 0.08)",
                            "&::before": {
                                content: '""',
                                position: "absolute",
                                inset: "auto 0 0 0",
                                height: 4,
                                background: "linear-gradient(90deg, #a7e5d3, #f4c5a8, #c8b8e0, #a8c8e8)",
                            },
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

import { alpha, createTheme, type PaletteMode } from "@mui/material/styles";

function buildTheme(mode: PaletteMode) {
    const isDark = mode === "dark";

    const ink = "#0c0a09";
    const warmInk = "#292524";
    const canvas = "#f5f5f5";
    const canvasSoft = "#fafafa";
    const hairline = "#e7e5e4";
    const darkCanvas = "#0c0a09";
    const darkPaper = "#1c1917";
    const mint = "#5fae9b";
    const sky = "#527da8";
    const peach = "#c98262";

    const theme = createTheme({
        palette: {
            mode,
            primary: {
                main: isDark ? "#f5f5f5" : warmInk,
                light: isDark ? "#ffffff" : "#57534e",
                dark: isDark ? "#d6d3d1" : ink,
                contrastText: isDark ? ink : "#ffffff",
            },
            secondary: {
                main: isDark ? "#a7e5d3" : mint,
                light: "#c8b8e0",
                dark: isDark ? "#74c7b4" : "#357e6e",
                contrastText: ink,
            },
            success: {
                main: isDark ? "#86d8a7" : "#2f8f57",
            },
            warning: {
                main: isDark ? "#f4c5a8" : peach,
            },
            error: {
                main: isDark ? "#f87171" : "#dc2626",
            },
            info: {
                main: isDark ? "#a8c8e8" : sky,
            },
            background: {
                default: isDark ? darkCanvas : canvas,
                paper: isDark ? darkPaper : canvasSoft,
            },
            text: {
                primary: isDark ? "#ffffff" : ink,
                secondary: isDark ? "#a8a29e" : "#57534e",
            },
            divider: isDark ? "rgba(255,255,255,0.12)" : hairline,
        },
        shape: {
            borderRadius: 2,
        },
        typography: {
            fontFamily:
                "'Manrope', ui-sans-serif, system-ui, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'",
            h1: {
                fontSize: "clamp(2.8rem, 6vw, 4rem)",
                fontWeight: 400,
                letterSpacing: 0,
                lineHeight: 1.05,
            },
            h2: {
                fontSize: "clamp(2.25rem, 4vw, 3rem)",
                fontWeight: 400,
                letterSpacing: 0,
                lineHeight: 1.08,
            },
            h3: {
                fontSize: "clamp(2rem, 3vw, 2.65rem)",
                fontWeight: 400,
                letterSpacing: 0,
                lineHeight: 1.12,
            },
            h4: {
                fontSize: "2rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.15,
            },
            h5: {
                fontSize: "1.875rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.2,
            },
            h6: {
                fontSize: "1.5rem",
                fontWeight: 400,
                letterSpacing: "normal",
                lineHeight: 1.33,
            },
            subtitle1: {
                fontSize: "1rem",
                fontWeight: 400,
            },
            subtitle2: {
                fontSize: "0.875rem",
                fontWeight: 400,
            },
            body1: {
                fontSize: "1rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            body2: {
                fontSize: "0.9rem",
                lineHeight: 1.5,
                fontWeight: 400,
            },
            button: {
                fontSize: "0.92rem",
                fontWeight: 700,
                textTransform: "none",
                letterSpacing: 0,
            },
            overline: {
                fontSize: "0.72rem",
                fontWeight: 400,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
            },
            caption: {
                fontSize: "0.875rem",
                lineHeight: 1.43,
                fontWeight: 400,
            },
        },
    });

    return createTheme(theme, {
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    ":root": {
                        colorScheme: mode,
                    },
                    "*, *::before, *::after": {
                        boxSizing: "border-box",
                    },
                    html: {
                        minHeight: "100%",
                        scrollBehavior: "smooth",
                    },
                    body: {
                        minHeight: "100vh",
                        margin: 0,
                        backgroundColor: isDark ? darkCanvas : canvas,
                        color: theme.palette.text.primary,
                        textRendering: "optimizeLegibility",
                        WebkitFontSmoothing: "antialiased",
                        MozOsxFontSmoothing: "grayscale",
                    },
                    "#root": {
                        minHeight: "100vh",
                    },
                    "::selection": {
                        backgroundColor: alpha(theme.palette.primary.main, 0.22),
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backdropFilter: "none",
                        backgroundImage: "none",
                        borderBottom: `1px solid ${theme.palette.divider}`,
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                        borderRadius: 8,
                    },
                    rounded: {
                        borderRadius: 8,
                    },
                },
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        border: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.paper,
                        boxShadow: isDark
                            ? "0 18px 50px rgba(0,0,0,0.32)"
                            : "0 18px 44px rgba(28,25,23,0.06)",
                    },
                },
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        minHeight: 44,
                        paddingInline: 18,
                        borderRadius: 999,
                        fontWeight: 700,
                    },
                    contained: {
                        backgroundColor: isDark ? "#f5f5f5" : warmInk,
                        color: isDark ? ink : "#ffffff",
                        "&:hover": {
                            backgroundColor: isDark ? "#d6d3d1" : ink,
                            color: isDark ? ink : "#ffffff",
                        },
                    },
                    outlined: {
                        borderColor: theme.palette.divider,
                        backgroundColor: isDark ? alpha(darkPaper, 0.86) : alpha("#ffffff", 0.76),
                    },
                    text: {
                        color: theme.palette.text.primary,
                        paddingTop: "8px",
                        paddingBottom: 0,
                    },
                    sizeSmall: {
                        minHeight: 36,
                        paddingInline: 14,
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                        fontWeight: 700,
                    },
                    outlined: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.12 : 0.1),
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        backgroundColor: isDark
                            ? alpha(darkPaper, 0.18)
                            : alpha("#ffffff", 0.9),
                        transition: theme.transitions.create(["border-color", "box-shadow", "background-color"]),
                        "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: alpha(theme.palette.primary.main, 0.34),
                        },
                        "&.Mui-focused": {
                            boxShadow: `0 0 0 4px ${alpha(theme.palette.primary.main, 0.14)}`,
                        },
                    },
                    notchedOutline: {
                        borderColor: theme.palette.divider,
                    },
                    input: {
                        paddingBlock: 14,
                    },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: {
                        fontWeight: 400,
                    },
                },
            },
            MuiAlert: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                    },
                    standardInfo: {
                        backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                    },
                },
            },
            MuiAvatar: {
                styleOverrides: {
                    root: {
                        fontWeight: 400,
                    },
                },
            },
            MuiDrawer: {
                styleOverrides: {
                    paper: {
                        borderRadius: 0,
                        borderRight: "none",
                        backgroundColor: isDark ? darkPaper : canvasSoft,
                    },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        minHeight: 48,
                        "&.Mui-selected": {
                            backgroundColor: alpha(theme.palette.secondary.main, isDark ? 0.2 : 0.16),
                            color: theme.palette.text.primary,
                            "& .MuiListItemIcon-root": {
                                color: theme.palette.secondary.dark,
                            },
                        },
                        "&:hover": {
                            backgroundColor: alpha(theme.palette.secondary.main, isDark ? 0.12 : 0.08),
                        },
                    },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    head: {
                        fontWeight: 700,
                        color: theme.palette.text.secondary,
                        backgroundColor: alpha(theme.palette.secondary.main, isDark ? 0.1 : 0.08),
                    },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        borderRadius: 6,
                        backgroundColor: alpha(theme.palette.text.primary, 0.9),
                        color: theme.palette.background.paper,
                        fontSize: "0.78rem",
                    },
                },
            },
            MuiSkeleton: {
                defaultProps: {
                    animation: "wave",
                },
            },
        },
    });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");

export type ColorMode = "light" | "dark" | "system";

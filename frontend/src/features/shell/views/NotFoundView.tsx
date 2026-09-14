import { Button, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { PageShell } from "../../../components/ui/PageShell";

type NotFoundViewProps = {
    /** Optional short context (e.g. inactive module) — keep terse. */
    detail?: string;
};

export default function NotFoundView({ detail }: NotFoundViewProps) {
    const navigate = useNavigate();

    return (
        <PageShell maxWidth="sm">
            <Stack spacing={3} sx={{ py: { xs: 6, md: 10 }, textAlign: "center" }}>
                <Typography variant="h3" component="h1" sx={{ fontWeight: 700 }}>
                    Page not found
                </Typography>
                {detail ? (
                    <Typography color="text.secondary">{detail}</Typography>
                ) : (
                    <Typography color="text.secondary">
                        This link is missing or no longer available.
                    </Typography>
                )}
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="center">
                    <Button variant="contained" onClick={() => navigate("/dashboard")}>
                        Go to dashboard
                    </Button>
                    <Button variant="outlined" onClick={() => navigate(-1)}>
                        Go back
                    </Button>
                </Stack>
            </Stack>
        </PageShell>
    );
}

import { useState } from "react";
import {
    Box,
    Button,
    Collapse,
    Drawer,
    IconButton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import { Close as CloseIcon, ContentCopy as CopyIcon } from "@mui/icons-material";
import type { RagEvalCandidate } from "../../../../api/ragEvaluation";
import { IdCell } from "../../../../components/ui/IdCell";

type CandidateTableProps = {
    candidates: RagEvalCandidate[];
};

/** Compact candidate table; chunk body opens in a right drawer. */
export function CandidateTable({ candidates }: CandidateTableProps) {
    const [selected, setSelected] = useState<RagEvalCandidate | null>(null);

    return (
        <>
            <Table size="small" stickyHeader>
                <TableHead>
                    <TableRow>
                        <TableCell>Rank</TableCell>
                        <TableCell>Document</TableCell>
                        <TableCell>Chunk</TableCell>
                        <TableCell>V/L</TableCell>
                        <TableCell>Scores</TableCell>
                        <TableCell>In</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {candidates.map((candidate) => (
                        <TableRow
                            key={candidate.chunk_id}
                            hover
                            sx={{ cursor: "pointer" }}
                            onClick={() => setSelected(candidate)}
                        >
                            <TableCell>{candidate.rank}</TableCell>
                            <TableCell>
                                <Typography variant="body2" noWrap sx={{ maxWidth: 160 }}>
                                    {candidate.filename || candidate.document_id}
                                </Typography>
                            </TableCell>
                            <TableCell onClick={(event) => event.stopPropagation()}>
                                <IdCell id={candidate.chunk_id} />
                            </TableCell>
                            <TableCell>
                                {candidate.vector_rank ?? "—"}/{candidate.lexical_rank ?? "—"}
                            </TableCell>
                            <TableCell>
                                <Typography
                                    variant="caption"
                                    component="span"
                                    sx={{ fontFamily: "ui-monospace, monospace" }}
                                >
                                    v={candidate.vector_score?.toFixed?.(3) ?? "—"} · l=
                                    {candidate.lexical_score?.toFixed?.(3) ?? "—"} · f=
                                    {candidate.fused_score?.toFixed?.(3) ?? "—"}
                                </Typography>
                            </TableCell>
                            <TableCell>{candidate.included ? "yes" : "no"}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>

            <Drawer
                anchor="right"
                open={Boolean(selected)}
                onClose={() => setSelected(null)}
                PaperProps={{ sx: { width: { xs: "100%", sm: 420 } } }}
            >
                {selected && (
                    <Box sx={{ p: 2.5 }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Typography variant="h6">Candidate #{selected.rank}</Typography>
                            <IconButton aria-label="Close candidate detail" onClick={() => setSelected(null)}>
                                <CloseIcon />
                            </IconButton>
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                            {selected.filename || selected.document_id}
                        </Typography>
                        <Box sx={{ mt: 1 }}>
                            <IdCell id={selected.chunk_id} label="Chunk ID" />
                        </Box>
                        <Typography variant="body2" sx={{ mt: 2, whiteSpace: "pre-wrap" }}>
                            {selected.content}
                        </Typography>
                    </Box>
                )}
            </Drawer>
        </>
    );
}

type AssembledContextViewerProps = {
    context: string;
};

export function AssembledContextViewer({ context }: AssembledContextViewerProps) {
    const [open, setOpen] = useState(true);
    const [copied, setCopied] = useState(false);
    const text = context || "(empty)";

    async function handleCopy() {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
        } catch {
            /* ignore */
        }
    }

    return (
        <Box>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Button size="small" onClick={() => setOpen((value) => !value)}>
                    {open ? "Hide" : "Show"} assembled context
                </Button>
                <Button
                    size="small"
                    startIcon={<CopyIcon fontSize="inherit" />}
                    onClick={() => void handleCopy()}
                >
                    {copied ? "Copied" : "Copy"}
                </Button>
            </Stack>
            <Collapse in={open}>
                <Typography
                    component="pre"
                    variant="body2"
                    sx={{
                        whiteSpace: "pre-wrap",
                        p: 1.5,
                        bgcolor: "action.hover",
                        borderRadius: 1,
                        maxHeight: 320,
                        overflow: "auto",
                        fontFamily: "ui-monospace, monospace",
                    }}
                >
                    {text}
                </Typography>
            </Collapse>
        </Box>
    );
}

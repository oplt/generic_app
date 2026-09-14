import {
    Button,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import type { RagIndexStatus } from "../../../../api/ragIndexes";
import { SectionCard } from "../../../../components/ui/SectionCard";
import { SectionTitleWithHelp } from "../../../../components/ui/SectionTitleWithHelp";
import type { RagIndexesModel } from "../../hooks/useRagIndexes";

type VersionsPanelProps = {
    data: RagIndexStatus;
    m: RagIndexesModel;
};

export function VersionsPanel({ data, m }: VersionsPanelProps) {
    return (
        <SectionCard
            title={
                <SectionTitleWithHelp
                    title="Index versions"
                    help="Lifecycle: building → validated → active → retired. Activate only after validation; rollback reuses retained chunks."
                />
            }
        >
            <Table size="small" stickyHeader>
                <TableHead>
                    <TableRow>
                        <TableCell>Key</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Model</TableCell>
                        <TableCell>Dims</TableCell>
                        <TableCell align="right">Actions</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {(data.versions ?? []).map((version) => (
                        <TableRow key={version.id} hover>
                            <TableCell>
                                <Typography
                                    variant="body2"
                                    sx={{ fontFamily: "ui-monospace, monospace" }}
                                >
                                    {version.key}
                                </Typography>
                            </TableCell>
                            <TableCell>{version.status}</TableCell>
                            <TableCell>
                                <Typography variant="body2" noWrap sx={{ maxWidth: 200 }}>
                                    {version.embedding_provider}/{version.embedding_model}
                                </Typography>
                            </TableCell>
                            <TableCell>{version.embedding_dimensions}</TableCell>
                            <TableCell align="right">
                                <Stack direction="row" spacing={1} justifyContent="flex-end">
                                    {version.status === "building" && (
                                        <Button
                                            size="small"
                                            onClick={() =>
                                                m.requestAction(
                                                    "validate",
                                                    version.id,
                                                    version.key
                                                )
                                            }
                                        >
                                            Validate
                                        </Button>
                                    )}
                                    {version.status === "validated" && (
                                        <Button
                                            size="small"
                                            variant="contained"
                                            onClick={() =>
                                                m.requestAction(
                                                    "activate",
                                                    version.id,
                                                    version.key
                                                )
                                            }
                                        >
                                            Activate
                                        </Button>
                                    )}
                                    {version.status === "retired" && (
                                        <Button
                                            size="small"
                                            color="warning"
                                            onClick={() =>
                                                m.requestAction(
                                                    "rollback",
                                                    version.id,
                                                    version.key
                                                )
                                            }
                                        >
                                            Rollback
                                        </Button>
                                    )}
                                </Stack>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </SectionCard>
    );
}

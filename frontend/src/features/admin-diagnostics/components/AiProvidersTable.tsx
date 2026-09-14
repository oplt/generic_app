import {
    Chip,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
} from "@mui/material";
import type { AiProviderDiagnostics, OperationalState } from "../../../api/diagnostics";
import { SectionCard } from "../../../components/ui/SectionCard";
import { diagnosticsStateColor } from "./diagnosticsStateColor";

export function AiProvidersTable({ providers }: { providers: AiProviderDiagnostics[] }) {
    return (
        <SectionCard title="AI providers">
            <Table size="small" stickyHeader>
                <TableHead>
                    <TableRow>
                        <TableCell>Provider</TableCell>
                        <TableCell>State</TableCell>
                        <TableCell>Configured</TableCell>
                        <TableCell>Detail</TableCell>
                        <TableCell>Latency (ms)</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {providers.map((provider) => (
                        <TableRow key={provider.key} hover>
                            <TableCell>{provider.label}</TableCell>
                            <TableCell>
                                <Chip
                                    size="small"
                                    label={provider.state}
                                    color={diagnosticsStateColor(provider.state as OperationalState)}
                                />
                            </TableCell>
                            <TableCell>{provider.configured ? "yes" : "no"}</TableCell>
                            <TableCell>{provider.detail}</TableCell>
                            <TableCell>
                                {provider.latency_summary_ms != null
                                    ? provider.latency_summary_ms.toFixed(1)
                                    : "—"}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </SectionCard>
    );
}

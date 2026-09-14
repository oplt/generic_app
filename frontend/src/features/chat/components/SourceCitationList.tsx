import { Chip, Link, Stack } from "@mui/material";
import { Description as DocumentIcon, Psychology as MemoryIcon } from "@mui/icons-material";
import type { ChatSource } from "../types";

export function SourceCitationList({ sources }: { sources: ChatSource[] }) {
    if (sources.length === 0) return null;
    return (
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {sources.map((source) => source.url ? (
                <Link key={source.source_id} href={source.url} target="_blank" rel="noreferrer" underline="hover" sx={{ fontSize: "0.8rem" }}>
                    {source.title}
                </Link>
            ) : (
                <Chip key={source.source_id} size="small" icon={source.kind === "memory" ? <MemoryIcon /> : <DocumentIcon />} label={source.kind === "memory" ? "Memory used" : source.available === false ? `${source.title} · unavailable` : `${source.title}${source.page_number ? ` · p.${source.page_number}` : ""}`} variant="outlined" title={source.snippet ?? undefined} />
            ))}
        </Stack>
    );
}

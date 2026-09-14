import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography } from "@mui/material";
import { CloudOutlined as CloudIcon, Computer as LocalIcon, Save as SaveIcon } from "@mui/icons-material";
import { getConfigSettings, updateConfigSettings, type ConfigSettingsResponse } from "../../../api/settings";
import type { AiProvider } from "../../../api/ai";
import { queryKeys } from "../../../config/queryKeys";
import { useAuth } from "../../../hooks/useAuth";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";
import { useSnackbar } from "../../../app/snackbarContext";
import { QueryErrorAlert } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";

type ProviderKey = "local" | "openai" | "anthropic";

const providerConfig: Record<ProviderKey, { model: string; baseUrl: string; label: string; description: string }> = {
    local: { model: "AI_LOCAL_MODEL_NAME", baseUrl: "", label: "Local", description: "Use the built-in local provider. No external API key required." },
    openai: { model: "OPENAI_DEFAULT_MODEL", baseUrl: "OPENAI_BASE_URL", label: "OpenAI", description: "Use OpenAI-compatible generation and embedding models." },
    anthropic: { model: "ANTHROPIC_DEFAULT_MODEL", baseUrl: "ANTHROPIC_BASE_URL", label: "Anthropic", description: "Use Anthropic for hosted generation." },
};

const providerIcons: Record<ProviderKey, React.ReactNode> = {
    local: <LocalIcon fontSize="small" />,
    openai: <CloudIcon fontSize="small" />,
    anthropic: <CloudIcon fontSize="small" />,
};

function configValue(data: ConfigSettingsResponse | undefined, key: string): string {
    return data?.items.find((item) => item.key === key)?.value ?? "";
}

function isProviderKey(value: string): value is ProviderKey {
    return value === "local" || value === "openai" || value === "anthropic";
}

export function AiProviderPanel({ providers }: { providers: AiProvider[] }) {
    const { isAdmin } = useAuth();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const toastError = useMutationErrorToast();
    const [providerOverride, setProviderOverride] = useState<ProviderKey | null>(null);
    const [modelNameOverride, setModelNameOverride] = useState<string | null>(null);
    const [baseUrlOverride, setBaseUrlOverride] = useState<string | null>(null);
    const [apiKey, setApiKey] = useState("");

    const config = useQuery({
        queryKey: queryKeys.settings.config,
        queryFn: getConfigSettings,
        enabled: isAdmin,
    });

    const configuredProvider = configValue(config.data, "AI_DEFAULT_PROVIDER");
    const providerKey = providerOverride ?? (isProviderKey(configuredProvider) ? configuredProvider : "local");
    const modelName = modelNameOverride ?? configValue(config.data, providerConfig[providerKey].model);
    const baseUrl = baseUrlOverride ?? (providerConfig[providerKey].baseUrl ? configValue(config.data, providerConfig[providerKey].baseUrl) : "");

    function selectProvider(nextProvider: ProviderKey) {
        setProviderOverride(nextProvider);
        setModelNameOverride(configValue(config.data, providerConfig[nextProvider].model));
        setBaseUrlOverride(providerConfig[nextProvider].baseUrl ? configValue(config.data, providerConfig[nextProvider].baseUrl) : "");
    }

    const configuredKey = useMemo(() => {
        if (providerKey === "openai") return configValue(config.data, "OPENAI_API_KEY");
        if (providerKey === "anthropic") return configValue(config.data, "ANTHROPIC_API_KEY");
        return "";
    }, [config.data, providerKey]);

    const saveMutation = useMutation({
        mutationFn: () => {
            const selected = providerConfig[providerKey];
            const items = [
                { key: "AI_DEFAULT_PROVIDER", value: providerKey },
                { key: selected.model, value: modelName.trim() },
                ...(selected.baseUrl ? [{ key: selected.baseUrl, value: baseUrl.trim() }] : []),
                ...(apiKey.trim() && providerKey !== "local" ? [{ key: `${providerKey === "openai" ? "OPENAI" : "ANTHROPIC"}_API_KEY`, value: apiKey.trim() }] : []),
            ];
            return updateConfigSettings({ items });
        },
        onSuccess: (data) => {
            queryClient.setQueryData(queryKeys.settings.config, data);
            setApiKey("");
            showToast({ message: `${providerConfig[providerKey].label} provider saved.`, severity: "success" });
        },
        onError: (error) => toastError(error, "Failed to save AI provider."),
    });

    const fallbackProviders: AiProvider[] = [
        { key: "local", label: "Local", supports_generation: true, supports_embeddings: true },
        { key: "openai", label: "OpenAI", supports_generation: true, supports_embeddings: true },
        { key: "anthropic", label: "Anthropic", supports_generation: true, supports_embeddings: false },
    ];
    const availableProviders = providers.filter((provider) => isProviderKey(provider.key));
    const providerOptions = availableProviders.length > 0 ? availableProviders : fallbackProviders;

    return (
        <SectionCard title="Add AI provider" description="Choose the generation provider used by new AI runs. API keys stay server-side and are never displayed after saving.">
            <Stack spacing={2.5}>
                <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" } }}>
                    {providerOptions.map((provider) => {
                        const key = provider.key as ProviderKey;
                        const selected = key === providerKey;
                        return (
                            <Box key={provider.key} role="button" tabIndex={0} onClick={() => selectProvider(key)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") selectProvider(key); }} sx={(theme) => ({ cursor: "pointer", p: 2, borderRadius: 3, border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`, backgroundColor: selected ? theme.palette.action.selected : theme.palette.background.paper })}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                                    <Stack direction="row" alignItems="center" spacing={1}><Box sx={{ display: "grid", placeItems: "center" }}>{providerIcons[key]}</Box><Typography variant="subtitle1">{providerConfig[key].label}</Typography></Stack>
                                    {selected && <Chip label="Selected" size="small" color="primary" />}
                                </Stack>
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{providerConfig[key].description}</Typography>
                                <Stack direction="row" spacing={0.75} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
                                    {provider.supports_generation && <Chip label="Generation" size="small" variant="outlined" />}
                                    {provider.supports_embeddings && <Chip label="Embeddings" size="small" variant="outlined" />}
                                </Stack>
                            </Box>
                        );
                    })}
                </Box>

                {!isAdmin ? (
                    <Alert severity="info">Provider changes require an administrator because they update shared server configuration. Your available providers are shown above.</Alert>
                ) : config.isError ? (
                    <QueryErrorAlert error={config.error} fallback="Failed to load AI provider settings." onRetry={() => void config.refetch()} />
                ) : (
                    <Stack spacing={2}>
                        <FormControl fullWidth>
                            <InputLabel id="ai-provider-select-label">Provider</InputLabel>
                            <Select labelId="ai-provider-select-label" label="Provider" value={providerKey} onChange={(event) => selectProvider(event.target.value as ProviderKey)}>
                                {Object.entries(providerConfig).map(([key, value]) => <MenuItem key={key} value={key}>{value.label}</MenuItem>)}
                            </Select>
                        </FormControl>
                        <TextField label="Model" value={modelName} onChange={(event) => setModelNameOverride(event.target.value)} placeholder={providerKey === "local" ? "local-heuristic" : providerKey === "openai" ? "gpt-4o-mini" : "claude-3-5-sonnet-latest"} fullWidth />
                        {providerKey !== "local" && <TextField label="Base URL (optional)" value={baseUrl} onChange={(event) => setBaseUrlOverride(event.target.value)} placeholder={providerKey === "openai" ? "https://api.openai.com/v1" : "https://api.anthropic.com"} fullWidth />}
                        {providerKey !== "local" && <TextField label={configuredKey === "********" ? "API key (leave blank to keep current)" : "API key"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} type="password" autoComplete="new-password" fullWidth />}
                        <Button variant="contained" startIcon={<SaveIcon />} onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !modelName.trim()}>{saveMutation.isPending ? "Saving..." : "Add provider"}</Button>
                    </Stack>
                )}
            </Stack>
        </SectionCard>
    );
}

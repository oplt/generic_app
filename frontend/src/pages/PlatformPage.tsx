import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControlLabel,
    Skeleton,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";
import {
    Bolt as BillingIcon,
    Flag as FlagIcon,
    Key as KeyIcon,
    Link as LinkIcon,
    Webhook as WebhookIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    createApiKey,
    createWebhook,
    deleteWebhook,
    getMySubscription,
    listApiKeys,
    listMyFeatureFlags,
    listSubscriptionPlans,
    listWebhooks,
    revokeApiKey,
    selectMyPlan,
    testWebhook,
    updateWebhook,
    type WebhookEndpoint,
} from "../api/platform";
import { useSnackbar } from "../app/snackbarContext";
import { queryKeys } from "../config/queryKeys";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SettingsTabs } from "../components/layout/SettingsTabs";
import { QueryErrorAlert } from "../components/ui/QueryBoundary";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { useMutationErrorToast } from "../hooks/useMutationErrorToast";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";
import { formatCurrency, formatDateTime } from "../utils/formatters";

const webhookTargetUrlSchema = z.string().url("Enter a valid URL (https://...)");

export default function PlatformPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const toastMutationError = useMutationErrorToast();
    const {
        data: metadata,
        isLoading: metadataLoading,
        isError: metadataIsError,
        error: metadataError,
        refetch: refetchMetadata,
    } = usePlatformMetadata();
    const enabledModules = metadata?.enabled_modules ?? [];
    const billingEnabled = enabledModules.includes("billing");
    const apiKeysEnabled = enabledModules.includes("api_keys");
    const webhooksEnabled = enabledModules.includes("webhooks");
    const flagsEnabled = enabledModules.includes("feature_flags");

    const {
        data: plans,
        isLoading: plansLoading,
        isError: plansIsError,
        error: plansError,
        refetch: refetchPlans,
    } = useQuery({
        queryKey: queryKeys.platform.plans,
        queryFn: listSubscriptionPlans,
        enabled: billingEnabled,
    });
    const {
        data: subscription,
        isLoading: subscriptionLoading,
        isError: subscriptionIsError,
        error: subscriptionError,
        refetch: refetchSubscription,
    } = useQuery({
        queryKey: queryKeys.platform.subscription,
        queryFn: getMySubscription,
        enabled: billingEnabled,
    });
    const {
        data: apiKeys,
        isLoading: apiKeysLoading,
        isError: apiKeysIsError,
        error: apiKeysError,
        refetch: refetchApiKeys,
    } = useQuery({
        queryKey: queryKeys.platform.apiKeys,
        queryFn: listApiKeys,
        enabled: apiKeysEnabled,
    });
    const {
        data: webhooks,
        isLoading: webhooksLoading,
        isError: webhooksIsError,
        error: webhooksError,
        refetch: refetchWebhooks,
    } = useQuery({
        queryKey: queryKeys.platform.webhooks,
        queryFn: listWebhooks,
        enabled: webhooksEnabled,
    });
    const {
        data: featureFlags,
        isLoading: featureFlagsLoading,
        isError: featureFlagsIsError,
        error: featureFlagsError,
        refetch: refetchFeatureFlags,
    } = useQuery({
        queryKey: queryKeys.platform.featureFlags,
        queryFn: listMyFeatureFlags,
        enabled: flagsEnabled,
    });

    const [apiKeyName, setApiKeyName] = useState("");
    const [apiKeyNameError, setApiKeyNameError] = useState<string | null>(null);
    const [revealedKey, setRevealedKey] = useState<string | null>(null);
    const [revealedWebhookSecret, setRevealedWebhookSecret] = useState<string | null>(null);
    const [webhookDraft, setWebhookDraft] = useState({
        target_url: "",
        description: "",
        events: "platform.test",
    });
    const [webhookUrlError, setWebhookUrlError] = useState<string | null>(null);
    const [lastWebhookResult, setLastWebhookResult] = useState("");

    const selectPlanMutation = useMutation({
        mutationFn: selectMyPlan,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.platform.subscription });
            showToast({ message: "Subscription updated.", severity: "success" });
        },
        onError: (error) => toastMutationError(error, "Failed to update subscription."),
    });
    const createApiKeyMutation = useMutation({
        mutationFn: createApiKey,
        onSuccess: async (data) => {
            setApiKeyName("");
            setRevealedKey(data.plaintext_key);
            await queryClient.invalidateQueries({ queryKey: queryKeys.platform.apiKeys });
        },
        onError: (error) => toastMutationError(error, "Failed to create API key."),
    });
    const revokeApiKeyMutation = useMutation({
        mutationFn: revokeApiKey,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.platform.apiKeys });
            showToast({ message: "API key revoked.", severity: "success" });
        },
        onError: (error) => toastMutationError(error, "Failed to revoke API key."),
    });
    const createWebhookMutation = useMutation({
        mutationFn: createWebhook,
        onSuccess: async (data) => {
            setWebhookDraft({ target_url: "", description: "", events: "platform.test" });
            setRevealedWebhookSecret(data.signing_secret);
            await queryClient.invalidateQueries({ queryKey: queryKeys.platform.webhooks });
            showToast({ message: "Webhook created.", severity: "success" });
        },
        onError: (error) => toastMutationError(error, "Failed to create webhook."),
    });
    const toggleWebhookMutation = useMutation({
        mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
            updateWebhook(id, { is_active }),
        onMutate: async ({ id, is_active }) => {
            await queryClient.cancelQueries({ queryKey: queryKeys.platform.webhooks });
            const previous = queryClient.getQueryData<WebhookEndpoint[]>(queryKeys.platform.webhooks);
            queryClient.setQueryData<WebhookEndpoint[]>(
                queryKeys.platform.webhooks,
                (old) => old?.map((webhook) => (webhook.id === id ? { ...webhook, is_active } : webhook))
            );
            return { previous };
        },
        onError: (error, _vars, context) => {
            if (context?.previous) {
                queryClient.setQueryData(queryKeys.platform.webhooks, context.previous);
            }
            toastMutationError(error, "Failed to update webhook.");
        },
        onSettled: () => void queryClient.invalidateQueries({ queryKey: queryKeys.platform.webhooks }),
    });
    const deleteWebhookMutation = useMutation({
        mutationFn: deleteWebhook,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.platform.webhooks });
            showToast({ message: "Webhook deleted.", severity: "success" });
        },
        onError: (error) => toastMutationError(error, "Failed to delete webhook."),
    });
    const testWebhookMutation = useMutation({
        mutationFn: testWebhook,
        onSuccess: (result) => {
            setLastWebhookResult(
                result.delivered
                    ? `Delivered with status ${result.status_code}.`
                    : result.error
                        ? `Delivery failed: ${result.error}`
                        : `Received status ${result.status_code}.`
            );
        },
        onError: (error) => toastMutationError(error, "Failed to test webhook."),
    });

    if (metadataLoading) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <Skeleton variant="rounded" width="90%" height={320} sx={{ borderRadius: 6 }} />
            </Box>
        );
    }

    if (metadataIsError || !metadata) {
        return (
            <PageShell maxWidth="xl">
                <SettingsTabs />
                <QueryErrorAlert
                    error={metadataError ?? new Error("Failed to load platform metadata.")}
                    fallback="Failed to load platform metadata."
                    onRetry={() => void refetchMetadata()}
                />
            </PageShell>
        );
    }

    const visibleUserModules =
        metadata?.module_catalog.filter((item) => item.user_visible && item.enabled) ?? [];

    return (
        <PageShell maxWidth="xl">
            <SettingsTabs />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        xl: "repeat(4, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label="Current plan"
                    value={subscription?.plan.name ?? "No plan"}
                    description="Subscription tier currently selected"
                    icon={<BillingIcon />}
                    loading={billingEnabled && subscriptionLoading}
                />
                <StatCard
                    label="API keys"
                    value={apiKeys?.length ?? 0}
                    description="Developer credentials available"
                    icon={<KeyIcon />}
                    loading={apiKeysEnabled && apiKeysLoading}
                    color="secondary"
                />
                <StatCard
                    label="Webhooks"
                    value={webhooks?.length ?? 0}
                    description="Outbound delivery endpoints configured"
                    icon={<WebhookIcon />}
                    loading={webhooksEnabled && webhooksLoading}
                    color="warning"
                />
                <StatCard
                    label="Feature flags"
                    value={featureFlags?.filter((flag) => flag.effective_enabled).length ?? 0}
                    description="Flags currently enabled for your account"
                    icon={<FlagIcon />}
                    loading={flagsEnabled && featureFlagsLoading}
                    color="success"
                />
            </Box>

            {visibleUserModules.length === 0 && (
                <Alert severity="info">
                    The active module pack does not expose any end-user platform modules right now.
                </Alert>
            )}

            {billingEnabled && (
                <SectionCard title="Billing" description="Review plans and switch when your usage changes.">
                    {(subscriptionIsError || plansIsError) && (
                        <QueryErrorAlert
                            error={subscriptionError ?? plansError}
                            fallback="Failed to load billing data."
                            onRetry={() => {
                                void refetchSubscription();
                                void refetchPlans();
                            }}
                        />
                    )}
                    {subscriptionLoading || plansLoading ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    sm: "repeat(2, minmax(0, 1fr))",
                                    lg: "repeat(3, minmax(0, 1fr))",
                                },
                            }}
                        >
                            {Array.from({ length: 3 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={200} sx={{ borderRadius: 4 }} />
                            ))}
                        </Box>
                    ) : (
                        <Stack spacing={2}>
                            <Alert severity="info">
                                Current plan: {subscription?.plan.name ?? "No plan selected"}
                            </Alert>
                            {(plans?.length ?? 0) === 0 ? (
                                <EmptyState
                                    icon={<BillingIcon />}
                                    title="No subscription plans yet"
                                    description="Plans will appear here once billing is configured for your workspace."
                                />
                            ) : (
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: {
                                        xs: "1fr",
                                        sm: "repeat(2, minmax(0, 1fr))",
                                        lg: "repeat(3, minmax(0, 1fr))",
                                    },
                                }}
                            >
                                {plans?.map((plan) => {
                                    const isCurrentPlan = subscription?.plan.code === plan.code;
                                    return (
                                        <Box
                                            key={plan.id}
                                            sx={(theme) => ({
                                                p: 2.5,
                                                borderRadius: 4,
                                                border: `1px solid ${theme.palette.divider}`,
                                                backgroundColor: isCurrentPlan
                                                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.06)
                                                    : theme.palette.background.paper,
                                                height: "100%",
                                            })}
                                        >
                                            <Stack spacing={1.5}>
                                                <Stack
                                                    direction={{ xs: "column", xl: "row" }}
                                                    justifyContent="space-between"
                                                    spacing={1.5}
                                                >
                                                    <Box>
                                                        <Typography variant="h6">{plan.name}</Typography>
                                                        <Typography variant="body2" color="text.secondary">
                                                            {plan.description || "Subscription plan"}
                                                        </Typography>
                                                    </Box>
                                                    <Typography variant="subtitle1">
                                                        {formatCurrency(plan.price_cents)}/{plan.interval}
                                                    </Typography>
                                                </Stack>
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                    {plan.features.map((feature) => (
                                                        <Chip key={feature} label={feature} size="small" variant="outlined" />
                                                    ))}
                                                </Stack>
                                                <Button
                                                    variant={isCurrentPlan ? "outlined" : "contained"}
                                                    disabled={selectPlanMutation.isPending || isCurrentPlan}
                                                    onClick={() => selectPlanMutation.mutate(plan.code)}
                                                >
                                                    {isCurrentPlan ? "Current plan" : "Switch plan"}
                                                </Button>
                                            </Stack>
                                        </Box>
                                    );
                                })}
                            </Box>
                            )}
                        </Stack>
                    )}
                </SectionCard>
            )}

            {apiKeysEnabled && (
                <SectionCard title="API keys" description="Create and revoke developer credentials with cleaner visibility.">
                    <Stack spacing={2}>
                        {apiKeysIsError && (
                            <QueryErrorAlert
                                error={apiKeysError}
                                fallback="Failed to load API keys."
                                onRetry={() => void refetchApiKeys()}
                            />
                        )}
                        {revealedKey && (
                            <Alert severity="success">
                                New key: <Typography component="span" sx={{ fontFamily: '"IBM Plex Mono", monospace' }}>{revealedKey}</Typography>. Copy it now. It will not be shown again.
                            </Alert>
                        )}
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                            <TextField
                                label="Key name"
                                value={apiKeyName}
                                onChange={(event) => {
                                    setApiKeyName(event.target.value);
                                    setApiKeyNameError(null);
                                }}
                                error={Boolean(apiKeyNameError)}
                                helperText={apiKeyNameError ?? "At least 2 characters. Shown in your key list only."}
                                fullWidth
                            />
                            <Button
                                variant="contained"
                                disabled={createApiKeyMutation.isPending || apiKeyName.trim().length < 2}
                                onClick={() => {
                                    const trimmed = apiKeyName.trim();
                                    if (trimmed.length < 2) {
                                        setApiKeyNameError("Key name must be at least 2 characters.");
                                        return;
                                    }
                                    createApiKeyMutation.mutate(trimmed);
                                }}
                            >
                                {createApiKeyMutation.isPending ? "Creating..." : "Create key"}
                            </Button>
                        </Stack>
                        {apiKeysLoading ? (
                            <Stack spacing={1.25}>
                                {Array.from({ length: 3 }).map((_, index) => (
                                    <Skeleton key={index} variant="rounded" height={92} sx={{ borderRadius: 4 }} />
                                ))}
                            </Stack>
                        ) : apiKeys && apiKeys.length > 0 ? (
                            <Stack spacing={1.25}>
                                {apiKeys.map((apiKey) => {
                                    const isRevokingThisKey =
                                        revokeApiKeyMutation.isPending &&
                                        revokeApiKeyMutation.variables === apiKey.id;
                                    return (
                                        <Box
                                            key={apiKey.id}
                                            sx={(theme) => ({
                                                p: 2.25,
                                                borderRadius: 4,
                                                border: `1px solid ${theme.palette.divider}`,
                                            })}
                                        >
                                            <Stack
                                                direction={{ xs: "column", sm: "row" }}
                                                justifyContent="space-between"
                                                spacing={1.5}
                                            >
                                                <Box>
                                                    <Typography variant="subtitle2">{apiKey.name}</Typography>
                                                    <Typography
                                                        variant="body2"
                                                        color="text.secondary"
                                                        sx={{ fontFamily: '"IBM Plex Mono", monospace' }}
                                                    >
                                                        Prefix {apiKey.key_prefix}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        Created {formatDateTime(apiKey.created_at)}
                                                        {apiKey.last_used_at ? ` • Last used ${formatDateTime(apiKey.last_used_at)}` : ""}
                                                    </Typography>
                                                </Box>
                                                <Button
                                                    variant="outlined"
                                                    color="error"
                                                    disabled={Boolean(apiKey.revoked_at) || isRevokingThisKey}
                                                    onClick={() => revokeApiKeyMutation.mutate(apiKey.id)}
                                                >
                                                    {apiKey.revoked_at ? "Revoked" : isRevokingThisKey ? "Revoking..." : "Revoke"}
                                                </Button>
                                            </Stack>
                                        </Box>
                                    );
                                })}
                            </Stack>
                        ) : (
                            <EmptyState
                                icon={<KeyIcon />}
                                title="No API keys yet"
                                description="Create a key when you are ready to integrate external systems or automation."
                            />
                        )}
                    </Stack>
                </SectionCard>
            )}

            {webhooksEnabled && (
                <SectionCard title="Webhooks" description="Configure delivery endpoints for outbound platform events.">
                    <Stack spacing={2}>
                        {webhooksIsError && (
                            <QueryErrorAlert
                                error={webhooksError}
                                fallback="Failed to load webhooks."
                                onRetry={() => void refetchWebhooks()}
                            />
                        )}
                        {revealedWebhookSecret && (
                            <Alert severity="success">
                                New webhook signing secret: <strong>{revealedWebhookSecret}</strong>
                            </Alert>
                        )}
                        {lastWebhookResult && <Alert severity="info">{lastWebhookResult}</Alert>}
                        <Box
                            sx={{
                                display: "grid",
                                gap: 2,
                                gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.9fr) minmax(0, 1.1fr)" },
                            }}
                        >
                            <Stack spacing={1.5}>
                                <TextField
                                    label="Target URL"
                                    value={webhookDraft.target_url}
                                    onChange={(event) => {
                                        setWebhookUrlError(null);
                                        setWebhookDraft((current) => ({
                                            ...current,
                                            target_url: event.target.value,
                                        }));
                                    }}
                                    error={Boolean(webhookUrlError)}
                                    helperText={webhookUrlError ?? "Must be a valid http(s) URL"}
                                    fullWidth
                                />
                                <TextField
                                    label="Description"
                                    value={webhookDraft.description}
                                    onChange={(event) =>
                                        setWebhookDraft((current) => ({ ...current, description: event.target.value }))
                                    }
                                    fullWidth
                                />
                                <TextField
                                    label="Events"
                                    value={webhookDraft.events}
                                    onChange={(event) =>
                                        setWebhookDraft((current) => ({ ...current, events: event.target.value }))
                                    }
                                    fullWidth
                                    helperText="Comma-separated event names"
                                />
                                <Button
                                    variant="contained"
                                    disabled={createWebhookMutation.isPending || webhookDraft.target_url.trim().length < 8}
                                    onClick={() => {
                                        const trimmedUrl = webhookDraft.target_url.trim();
                                        const parsed = webhookTargetUrlSchema.safeParse(trimmedUrl);
                                        if (!parsed.success) {
                                            setWebhookUrlError(parsed.error.issues[0]?.message ?? "Invalid URL");
                                            return;
                                        }
                                        createWebhookMutation.mutate({
                                            target_url: trimmedUrl,
                                            description: webhookDraft.description.trim() || undefined,
                                            events: webhookDraft.events
                                                .split(",")
                                                .map((item) => item.trim())
                                                .filter(Boolean),
                                        });
                                    }}
                                >
                                    {createWebhookMutation.isPending ? "Creating..." : "Create webhook"}
                                </Button>
                            </Stack>

                            {webhooksLoading ? (
                                <Stack spacing={1.25}>
                                    {Array.from({ length: 2 }).map((_, index) => (
                                        <Skeleton key={index} variant="rounded" height={148} sx={{ borderRadius: 4 }} />
                                    ))}
                                </Stack>
                            ) : webhooks && webhooks.length > 0 ? (
                                <Stack spacing={1.25}>
                                    {webhooks.map((webhook) => {
                                        const isTestingThisWebhook =
                                            testWebhookMutation.isPending &&
                                            testWebhookMutation.variables === webhook.id;
                                        const isDeletingThisWebhook =
                                            deleteWebhookMutation.isPending &&
                                            deleteWebhookMutation.variables === webhook.id;
                                        const isTogglingThisWebhook =
                                            toggleWebhookMutation.isPending &&
                                            toggleWebhookMutation.variables?.id === webhook.id;

                                        return (
                                            <Box
                                                key={webhook.id}
                                                sx={(theme) => ({
                                                    p: 2.25,
                                                    borderRadius: 4,
                                                    border: `1px solid ${theme.palette.divider}`,
                                                })}
                                            >
                                                <Stack spacing={1.5}>
                                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                                                        <Box>
                                                            <Typography variant="subtitle2">{webhook.target_url}</Typography>
                                                            {webhook.description && (
                                                                <Typography variant="body2" color="text.secondary">
                                                                    {webhook.description}
                                                                </Typography>
                                                            )}
                                                        </Box>
                                                        <FormControlLabel
                                                            control={
                                                                <Switch
                                                                    checked={webhook.is_active}
                                                                    disabled={isTogglingThisWebhook}
                                                                    onChange={(event) =>
                                                                        toggleWebhookMutation.mutate({
                                                                            id: webhook.id,
                                                                            is_active: event.target.checked,
                                                                        })
                                                                    }
                                                                />
                                                            }
                                                            label="Active"
                                                        />
                                                    </Stack>
                                                    <Typography
                                                        variant="body2"
                                                        color="text.secondary"
                                                        sx={{ fontFamily: '"IBM Plex Mono", monospace' }}
                                                    >
                                                        Signing secret is hidden after creation. Rotate by recreating the webhook if needed.
                                                    </Typography>
                                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                        {webhook.events.map((eventName) => (
                                                            <Chip key={eventName} label={eventName} size="small" />
                                                        ))}
                                                    </Stack>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {webhook.last_tested_at
                                                            ? `Last tested ${formatDateTime(webhook.last_tested_at)}`
                                                            : "Not tested yet"}
                                                        {webhook.last_response_status
                                                            ? ` • Last status ${webhook.last_response_status}`
                                                            : ""}
                                                    </Typography>
                                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            startIcon={<LinkIcon />}
                                                            disabled={isTestingThisWebhook}
                                                            onClick={() => testWebhookMutation.mutate(webhook.id)}
                                                        >
                                                            {isTestingThisWebhook ? "Testing..." : "Test delivery"}
                                                        </Button>
                                                        <Button
                                                            variant="outlined"
                                                            color="error"
                                                            size="small"
                                                            disabled={isDeletingThisWebhook}
                                                            onClick={() => deleteWebhookMutation.mutate(webhook.id)}
                                                        >
                                                            {isDeletingThisWebhook ? "Deleting..." : "Delete"}
                                                        </Button>
                                                    </Stack>
                                                </Stack>
                                            </Box>
                                        );
                                    })}
                                </Stack>
                            ) : (
                                <EmptyState
                                    icon={<WebhookIcon />}
                                    title="No webhooks configured"
                                    description="Create an endpoint to push platform events into your own systems."
                                />
                            )}
                        </Box>
                    </Stack>
                </SectionCard>
            )}

            {flagsEnabled && (
                <SectionCard title="Feature flags" description="These flags are active for your account based on current platform configuration.">
                    {featureFlagsIsError && (
                        <QueryErrorAlert
                            error={featureFlagsError}
                            fallback="Failed to load feature flags."
                            onRetry={() => void refetchFeatureFlags()}
                        />
                    )}
                    {featureFlagsLoading ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            {Array.from({ length: 3 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={144} sx={{ borderRadius: 4 }} />
                            ))}
                        </Box>
                    ) : featureFlags && featureFlags.length > 0 ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            {featureFlags.map((flag) => (
                                <Box
                                    key={flag.id}
                                    sx={(theme) => ({
                                        p: 2.25,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" justifyContent="space-between" spacing={1}>
                                            <Box>
                                                <Typography variant="subtitle2">{flag.name}</Typography>
                                                <Typography variant="body2" color="text.secondary">
                                                    {flag.key}
                                                </Typography>
                                            </Box>
                                            <Chip
                                                label={flag.effective_enabled ? "Enabled for you" : "Off"}
                                                color={flag.effective_enabled ? "success" : "default"}
                                                size="small"
                                            />
                                        </Stack>
                                        {flag.description && (
                                            <Typography variant="body2" color="text.secondary">
                                                {flag.description}
                                            </Typography>
                                        )}
                                    </Stack>
                                </Box>
                            ))}
                        </Box>
                    ) : (
                        <EmptyState
                            icon={<FlagIcon />}
                            title="No feature flags configured"
                            description="Flags will appear here when the platform exposes rollout-based capabilities."
                        />
                    )}
                </SectionCard>
            )}
        </PageShell>
    );
}

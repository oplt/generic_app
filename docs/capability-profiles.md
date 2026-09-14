# Starter capability profiles

Capability profiles are deterministic named slices of the platform built on
[module manifests](module-manifests.md). They extend — rather than replace —
module packs: each profile key is also a `MODULE_PACKS` entry.

Profiles never install packages at runtime. They only select modules already
registered in `backend/modules/manifests/registry.py`.

Feature onboarding: [adding-a-feature.md](adding-a-feature.md).

## Profiles

| Key | Extends | Optional modules | Intent |
| --- | --- | --- | --- |
| `core` | — | _(none)_ | Auth, users, profiles, projects, settings, observability |
| `lean_saas` | core | billing, api_keys, feature_flags | Straightforward SaaS clone |
| `rag` | core | _(none)_ | AI providers + document RAG (always-on AI/RAG stack) |
| `agent` | rag | _(none)_ | RAG + chat/agent runtime + memory |
| `automation_suite` | core | api_keys, webhooks, feature_flags, email_templates | Workflow / integrations |
| `client_portal` | core | billing, feature_flags, email_templates | Subscription-led portal |
| `full_platform` | core | all optional catalog keys | Everything stable |

Source: `backend/modules/platform/profiles.py`.

Generated modules default to `--optional` so they do **not** appear in every
profile. Attach a specialist with:

```bash
./scripts/generic-app create-module inventory --crud --frontend --profile rag
```

That appends the key under `PROFILE_EXTRA_MODULES` for `rag` (and any profile
that extends it only if you also list it there — extras are per-profile).

## What a profile resolves

`resolve_capability_profile(key)` / `resolve_active_modules(key)` return:

- `active_modules` (always-on + optional)
- `backend_router_keys`, `celery_queues`, `scheduled_tasks`
- `frontend_routes` / nav contributions
- `settings_prefixes`, `health_checks`, `required_permissions`
- `feature_flags` declared on manifests + `recommended_feature_flags`
- `health_checks` used at readiness (e.g. storage/vector only when the profile
  needs them — see [startup-dependencies.md](startup-dependencies.md))

Optional routers (billing, webhooks, …) still call `ensure_module_enabled`.
Celery workers should be started with the queues listed on the active profile
(`celery_queues`); the API does not dynamically install workers.

## Validation

Startup (and tests) call:

```python
from backend.modules.platform.profiles import validate_capability_profiles

validate_capability_profiles()
```

Failures include unknown modules, broken `extends` cycles, and missing expected
routers/queues for a profile. Architecture tests also assert core vs rag slices
differ ([testing-architecture.md](testing-architecture.md)).

## Configuration

- Setting key: `platform.module_pack` (unchanged for compatibility)
- Value: a capability profile key (`core`, `lean_saas`, `rag`, …)
- Env default: `PLATFORM_DEFAULT_MODULE_PACK` (default `full_platform`)

Platform metadata/config also exposes:

- `capability_profile` — alias of `module_pack`
- `active_profile` — resolved matrix for the active profile
- `available_capability_profiles` — matrix for every profile

Admin UI “Capability profile” selector writes the same setting.

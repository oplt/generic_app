"""Policy / RBAC module public exports."""

from backend.modules.policy.deps import authorize, require_permission
from backend.modules.policy.service import PolicyService

__all__ = ["PolicyService", "authorize", "require_permission"]

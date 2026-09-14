"""Integration matrix for multi-organization project tenancy."""

from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import select

from backend.modules.identity_access.models import (
    Organization,
    OrganizationMembership,
    User,
)
from backend.modules.projects.models import Project
from backend.tests.integration_support import (
    api_client,
    auth_request,
    ensure_integration_schema,
    integration_enabled,
    register_user,
    sign_in,
    unique_email,
)


@unittest.skipUnless(
    integration_enabled(),
    "Set RUN_INTEGRATION_TESTS=1 and migrate postgres (alembic upgrade head)",
)
class MultiOrgTenantIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_project_organization_is_authoritative_for_scope_and_assignment(self):
        self.assertTrue(await ensure_integration_schema())
        email = unique_email("multi-org-owner")
        other_email = unique_email("multi-org-outsider")

        async with api_client() as client:
            await register_user(client, email=email)
            await register_user(client, email=other_email)

            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                owner = await db.scalar(select(User).where(User.email == email))
                outsider = await db.scalar(select(User).where(User.email == other_email))
                assert owner is not None and outsider is not None
                default_org_id = await db.scalar(
                    select(OrganizationMembership.organization_id)
                    .where(OrganizationMembership.user_id == owner.id)
                    .order_by(
                        OrganizationMembership.created_at.asc(),
                        OrganizationMembership.id.asc(),
                    )
                    .limit(1)
                )
                second_org = Organization(
                    id=str(uuid4()), name=f"Second org {uuid4().hex[:8]}"
                )
                db.add(second_org)
                db.add(
                    OrganizationMembership(
                        organization_id=second_org.id,
                        user_id=owner.id,
                        role="owner",
                    )
                )
                await db.commit()
                owner_id = owner.id
                outsider_id = outsider.id
                org_a = default_org_id
                org_b = second_org.id

            await sign_in(client, email=email)
            project_b = await auth_request(
                client,
                "POST",
                "/api/v1/projects",
                json={"name": "Org B project", "organization_id": org_b},
            )
            self.assertEqual(project_b.status_code, 201, project_b.text)
            body = project_b.json()
            self.assertEqual(body["organization_id"], org_b)
            project_id = body["id"]

            denied = await auth_request(
                client,
                "POST",
                f"/api/v1/projects/{project_id}/tasks",
                json={"title": "Cross org", "assignee_id": outsider_id},
            )
            self.assertEqual(denied.status_code, 404)

            async with SessionLocal() as db:
                project = await db.scalar(select(Project).where(Project.id == project_id))
                assert project is not None
                self.assertEqual(project.organization_id, org_b)
                self.assertNotEqual(project.organization_id, org_a)
                self.assertEqual(project.owner_id, owner_id)

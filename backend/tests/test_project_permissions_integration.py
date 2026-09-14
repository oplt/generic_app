import unittest

from sqlalchemy import select

from backend.modules.identity_access.models import OrganizationMembership, User
from backend.modules.projects.models import ProjectTask
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
class ProjectPermissionsIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_project_read_and_task_mutation_permissions(self):
        self.assertTrue(await ensure_integration_schema())
        emails = {
            role: unique_email(f"project-{role}")
            for role in ("owner", "member", "unassigned", "different-org")
        }

        async with api_client() as client:
            for email in emails.values():
                await register_user(client, email=email)

            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                users = {
                    role: await db.scalar(select(User).where(User.email == email))
                    for role, email in emails.items()
                }
                owner_org_id = await db.scalar(
                    select(OrganizationMembership.organization_id)
                    .where(OrganizationMembership.user_id == users["owner"].id)
                    .order_by(
                        OrganizationMembership.created_at.asc(),
                        OrganizationMembership.id.asc(),
                    )
                    .limit(1)
                )
                for role in ("member", "unassigned"):
                    db.add(
                        OrganizationMembership(
                            organization_id=owner_org_id,
                            user_id=users[role].id,
                            role="member",
                        )
                    )
                await db.commit()
                user_ids = {role: user.id for role, user in users.items()}

            await sign_in(client, email=emails["owner"])
            created_project = await auth_request(
                client,
                "POST",
                "/api/v1/projects",
                json={"name": "Permission boundary"},
            )
            self.assertEqual(created_project.status_code, 201, created_project.text)
            project_id = created_project.json()["id"]

            cross_org_assignment = await auth_request(
                client,
                "POST",
                f"/api/v1/projects/{project_id}/tasks",
                json={
                    "title": "Invalid assignment",
                    "assignee_id": user_ids["different-org"],
                },
            )
            self.assertEqual(cross_org_assignment.status_code, 404)

            assigned_task = await auth_request(
                client,
                "POST",
                f"/api/v1/projects/{project_id}/tasks",
                json={"title": "Assigned task", "assignee_id": user_ids["member"]},
            )
            self.assertEqual(assigned_task.status_code, 201, assigned_task.text)
            task_id = assigned_task.json()["id"]

            owner_task = await auth_request(
                client,
                "POST",
                f"/api/v1/projects/{project_id}/tasks",
                json={"title": "Owner task"},
            )
            self.assertEqual(owner_task.status_code, 201, owner_task.text)
            owner_task_id = owner_task.json()["id"]

            owner_update = await auth_request(
                client,
                "PATCH",
                f"/api/v1/projects/{project_id}/tasks/{owner_task_id}",
                json={"status": "in_progress"},
            )
            self.assertEqual(owner_update.status_code, 200, owner_update.text)
            owner_reorder = await auth_request(
                client,
                "PUT",
                f"/api/v1/projects/{project_id}/tasks/reorder",
                json={
                    "columns": [
                        {"status": "todo", "task_ids": [task_id, owner_task_id]},
                    ]
                },
            )
            self.assertEqual(owner_reorder.status_code, 200, owner_reorder.text)
            owner_delete = await auth_request(
                client,
                "DELETE",
                f"/api/v1/projects/{project_id}/tasks/{owner_task_id}",
            )
            self.assertEqual(owner_delete.status_code, 204, owner_delete.text)

            await sign_in(client, email=emails["member"])
            member_projects = await client.get("/api/v1/projects")
            self.assertIn(project_id, {item["id"] for item in member_projects.json()["items"]})
            self.assertEqual((await client.get(f"/api/v1/projects/{project_id}")).status_code, 200)
            self.assertEqual(
                (await client.get(f"/api/v1/projects/{project_id}/tasks")).status_code,
                200,
            )
            denied_mutations = (
                await auth_request(
                    client,
                    "POST",
                    f"/api/v1/projects/{project_id}/tasks",
                    json={"title": "Forbidden create"},
                ),
                await auth_request(
                    client,
                    "PATCH",
                    f"/api/v1/projects/{project_id}/tasks/{task_id}",
                    json={"status": "done"},
                ),
                await auth_request(
                    client,
                    "DELETE",
                    f"/api/v1/projects/{project_id}/tasks/{task_id}",
                ),
                await auth_request(
                    client,
                    "PUT",
                    f"/api/v1/projects/{project_id}/tasks/reorder",
                    json={"columns": [{"status": "todo", "task_ids": [task_id]}]},
                ),
            )
            self.assertEqual([response.status_code for response in denied_mutations], [404] * 4)

            for role in ("unassigned", "different-org"):
                await sign_in(client, email=emails[role])
                project_list = await client.get("/api/v1/projects")
                self.assertNotIn(
                    project_id,
                    {item["id"] for item in project_list.json()["items"]},
                )
                self.assertEqual(
                    (await client.get(f"/api/v1/projects/{project_id}")).status_code,
                    404,
                )
                self.assertEqual(
                    (await client.get(f"/api/v1/projects/{project_id}/tasks")).status_code,
                    404,
                )
                denied_create = await auth_request(
                    client,
                    "POST",
                    f"/api/v1/projects/{project_id}/tasks",
                    json={"title": "Forbidden create"},
                )
                self.assertEqual(denied_create.status_code, 404)

            async with SessionLocal() as db:
                db.add(
                    ProjectTask(
                        project_id=project_id,
                        assignee_id=user_ids["different-org"],
                        title="Legacy cross-organization assignment",
                    )
                )
                await db.commit()

            self.assertEqual(
                (await client.get(f"/api/v1/projects/{project_id}")).status_code,
                404,
            )
            project_list = await client.get("/api/v1/projects")
            self.assertNotIn(
                project_id,
                {item["id"] for item in project_list.json()["items"]},
            )

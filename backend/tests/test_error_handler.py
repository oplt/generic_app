import json
import unittest

from fastapi import FastAPI
from starlette.requests import Request

from backend.core.error_handler import register_exception_handlers


class ErrorHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_value_error_returns_stable_safe_error_contract(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/bad",
                "headers": [],
                "query_string": b"",
            }
        )
        handler = app.exception_handlers[ValueError]
        response = await handler(request, ValueError("database details must not leak"))
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["detail"], "The request contains invalid data.")
        self.assertEqual(payload["error_code"], "invalid_request")

import unittest

from backend.core.uploads import (
    UploadTooLargeError,
    detect_image_content_type,
    read_upload_limited,
)
from backend.modules.rag.application.rag_policy_service import RagPolicyService


class UploadSafetyTest(unittest.IsolatedAsyncioTestCase):
    class FakeUpload:
        def __init__(self, content: bytes, headers: dict[str, str] | None = None):
            self.content = content
            self.headers = headers or {}
            self.read_calls = 0

        async def read(self, size: int) -> bytes:
            self.read_calls += 1
            chunk, self.content = self.content[:size], self.content[size:]
            return chunk

    async def test_content_length_rejects_before_stream_read(self):
        upload = self.FakeUpload(b"0123456789", headers={"content-length": "10"})
        with self.assertRaises(UploadTooLargeError):
            await read_upload_limited(upload, max_bytes=5)
        self.assertEqual(upload.read_calls, 0)

    async def test_upload_reader_rejects_oversized_streams(self):
        upload = self.FakeUpload(b"0123456789")
        with self.assertRaises(UploadTooLargeError):
            await read_upload_limited(upload, max_bytes=5, chunk_size=2)

    async def test_upload_reader_accepts_content_under_limit(self):
        upload = self.FakeUpload(b"hello")
        self.assertEqual(await read_upload_limited(upload, max_bytes=5), b"hello")


class UploadSignatureTest(unittest.TestCase):
    def test_signatures_match_allowed_document_types(self):
        policy = RagPolicyService()
        self.assertTrue(policy.has_valid_file_signature("notes.txt", b"hello"))
        self.assertTrue(policy.has_valid_file_signature("report.pdf", b"%PDF-1.7"))
        self.assertFalse(policy.has_valid_file_signature("report.pdf", b"plain text"))
        self.assertFalse(policy.has_valid_file_signature("notes.txt", b"bad\x00data"))

    def test_image_signature_detection_ignores_client_mime(self):
        self.assertEqual(detect_image_content_type(b"\x89PNG\r\n\x1a\n..."), "image/png")
        self.assertEqual(detect_image_content_type(b"\xff\xd8\xff..."), "image/jpeg")
        self.assertIsNone(detect_image_content_type(b"not-an-image"))

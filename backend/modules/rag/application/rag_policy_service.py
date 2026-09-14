from __future__ import annotations

import re

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore (all )?(previous|prior|system) (instructions|rules)"),
    re.compile(r"(?i)ignore (all )?(previous|prior) (system )?(instructions|rules)"),
    re.compile(r"(?i)you are now (in )?developer mode"),
    re.compile(r"(?i)reveal (the )?(secret|password|api[_-]?key|token)"),
    re.compile(r"(?i)override (system|developer|safety)"),
)


class RagPolicyService:
    def find_prompt_injection(self, content: str) -> dict[str, object] | None:
        for pattern in INJECTION_PATTERNS:
            match = pattern.search(content)
            if match:
                return {
                    "pattern": pattern.pattern,
                    "start": match.start(),
                    "end": match.end(),
                    "span": match.group(0)[:240],
                }
        return None

    def contains_prompt_injection(self, content: str) -> bool:
        return self.find_prompt_injection(content) is not None

    def is_allowed_file_type(self, filename: str, allowed: tuple[str, ...]) -> bool:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return suffix in allowed

    def has_valid_file_signature(self, filename: str, content: bytes) -> bool:
        return self.detect_content_type(filename, content) is not None

    def detect_content_type(self, filename: str, content: bytes) -> str | None:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix == "pdf":
            return "application/pdf" if content.startswith(b"%PDF-") else None
        if suffix == "docx":
            return (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if content.startswith(b"PK\x03\x04")
                else None
            )
        if suffix in {"txt", "md", "csv"}:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                return None
            if b"\x00" in content:
                return None
            return {
                "txt": "text/plain",
                "md": "text/markdown",
                "csv": "text/csv",
            }[suffix]
        return None

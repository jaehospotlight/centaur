"""Unit tests for attachment model and ExecuteRequest integration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pydantic import ValidationError

from api.routers.agent import Attachment, ExecuteRequest


class TestAttachmentModel:
    def test_valid_attachment(self):
        att = Attachment(name="test.pdf", mime_type="application/pdf", data="dGVzdA==")
        assert att.name == "test.pdf"
        assert att.mime_type == "application/pdf"
        assert att.data == "dGVzdA=="

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            Attachment(name="test.pdf")  # missing mime_type and data

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            Attachment(mime_type="text/plain", data="dGVzdA==")


class TestExecuteRequestAttachments:
    def test_with_attachments(self):
        req = ExecuteRequest(
            thread_key="test:1",
            message="analyze this",
            attachments=[
                Attachment(name="doc.pdf", mime_type="application/pdf", data="dGVzdA==")
            ],
        )
        assert req.attachments is not None
        assert len(req.attachments) == 1
        assert req.attachments[0].name == "doc.pdf"

    def test_without_attachments(self):
        req = ExecuteRequest(thread_key="test:1", message="hello")
        assert req.attachments is None

    def test_empty_attachments_list(self):
        req = ExecuteRequest(thread_key="test:1", message="hello", attachments=[])
        assert req.attachments == []

    def test_multiple_attachments(self):
        req = ExecuteRequest(
            thread_key="test:1",
            message="review these",
            attachments=[
                Attachment(name="a.png", mime_type="image/png", data="aWduZw=="),
                Attachment(name="b.csv", mime_type="text/csv", data="Zm9v"),
            ],
        )
        assert len(req.attachments) == 2

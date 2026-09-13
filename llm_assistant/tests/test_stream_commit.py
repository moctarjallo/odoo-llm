from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestStreamCommit(TransactionCase):
    """Streaming commits flush partial output to a watching browser. Inside a
    queue job there is none, and queue_job forbids the commit outright —
    RuntimeError("Commit is forbidden in queue jobs"), which surfaced to a
    WhatsApp user as "LLM API Error" once the reply pipeline got far enough to
    stream (live on smartacus, 2026-09-13).

    The cursor is patched per instance, not on the class: TransactionCase
    installs its own commit guard on the cursor object, so a class-level patch
    is bypassed and the test hits Odoo's "Cannot commit ... from inside a test".
    """

    def setUp(self):
        super().setUp()
        provider = self.env["llm.provider"].create(
            {"name": "Stream Commit Provider", "service": "openai", "api_key": "k"},
        )
        model = self.env["llm.model"].create(
            {
                "name": "stream-commit-model",
                "provider_id": provider.id,
                "model_use": "chat",
            },
        )
        self.thread = self.env["llm.thread"].create(
            {
                "name": "Stream Commit Thread",
                "provider_id": provider.id,
                "model_id": model.id,
                "user_id": self.env.user.id,
            },
        )

    def test_commits_when_a_browser_may_be_watching(self):
        with patch.object(self.env.cr, "commit") as commit:
            self.thread._stream_commit()
        commit.assert_called_once()

    def test_does_not_commit_inside_a_queue_job(self):
        """queue_job stamps job_uuid on the running job's context
        (job.py: recordset.with_context(job_uuid=self.uuid))."""
        in_job = self.thread.with_context(job_uuid="0c5f1e3a-dead-beef")
        with patch.object(self.env.cr, "commit") as commit:
            in_job._stream_commit()
        commit.assert_not_called()

    def test_a_forbidding_cursor_is_never_reached_inside_a_job(self):
        """The regression itself: with queue_job's forbidden_commit installed,
        reaching the cursor raises. The helper must return before it does.
        """

        def forbidden_commit(*args, **kwargs):
            raise RuntimeError("Commit is forbidden in queue jobs.")

        in_job = self.thread.with_context(job_uuid="0c5f1e3a-dead-beef")
        with patch.object(self.env.cr, "commit", forbidden_commit):
            in_job._stream_commit()

from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from reminder import Canvas, collect, render, send


class FakeCanvas:
    def pages(self, path, params):
        if path == "courses":
            return iter([{"id": 42, "name": "Computer Architecture"}])
        if path == "announcements":
            return iter([{"title": "Office hours", "message": "<p>Tomorrow &amp; Friday</p>",
                          "posted_at": "2026-10-15T12:00:00Z"}])
        return iter([
            {"name": "Overdue", "due_at": "2026-10-14T12:00:00Z"},
            {"name": "Submitted", "submission": {"workflow_state": "submitted"}},
            {"name": "Excused", "submission": {"excused": True}},
            {"name": "Missing zero", "submission": {"workflow_state": "graded", "missing": True}},
            {"name": "Unpublished", "published": False},
            {"name": "Later", "due_at": "2027-01-01T12:00:00Z"},
            {"name": "Upcoming", "due_at": "2026-10-17T18:00:00Z"},
            {"name": "No deadline"},
        ])


class ReminderTests(unittest.TestCase):
    def test_digest_filters_and_localizes_actual_canvas_shapes(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        assignments, announcements = collect(FakeCanvas(), now, 14)
        self.assertEqual([a["title"] for a in assignments],
                         ["Overdue", "Upcoming", "Missing zero", "No deadline"])
        digest = render(assignments, announcements, now, ZoneInfo("America/Los_Angeles"), 14)
        self.assertIn("ATRASADA", digest)
        self.assertIn("17/10 às 11:00", digest)
        self.assertIn("Tomorrow & Friday", digest)
        self.assertNotIn("<p>", digest)

    @patch("urllib.request.build_opener")
    def test_canvas_follows_pagination(self, build):
        def response(data, link=""):
            result = MagicMock()
            result.__enter__.return_value = result
            result.read.return_value = json.dumps(data).encode()
            result.headers = {"Link": link}
            return result
        opener = build.return_value
        opener.open.side_effect = [response([{"id": 1}], '<https://bcourses.berkeley.edu/api/v1/courses?page=2>; rel="next"'),
                                   response([{"id": 2}])]
        rows = list(Canvas("https://bcourses.berkeley.edu", "test-token").pages("courses"))
        self.assertEqual(rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(opener.open.call_count, 2)

    @patch("urllib.request.build_opener")
    def test_canvas_rejects_foreign_pagination_before_sending_token(self, build):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"[]"
        response.headers = {"Link": '<https://other.example/api>; rel="next"'}
        build.return_value.open.return_value = response
        with self.assertRaises(ValueError):
            list(Canvas("https://bcourses.berkeley.edu", "test-token").pages("courses"))
        self.assertEqual(build.return_value.open.call_count, 1)

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
    @patch("reminder.urlopen")
    def test_telegram_delivers_every_chunk(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"ok": true}'
        send("a" * 4000, "telegram")
        bodies = [json.loads(call.args[0].data) for call in urlopen.call_args_list]
        self.assertEqual("".join(b["text"] for b in bodies), "a" * 4000)
        self.assertTrue(all(b["chat_id"] == "123" for b in bodies))


if __name__ == "__main__":
    unittest.main()

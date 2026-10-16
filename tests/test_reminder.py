from datetime import datetime, timezone
from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from reminder import Canvas, collect, render, send, run, delivery_key, main


class FakeCanvas:
    def pages(self, path, params):
        if path == "courses":
            return iter([{"id": 42, "name": "Computer Architecture"}])
        if path == "announcements":
            return iter([{"title": "Office hours", "message": "<p>Tomorrow &amp; Friday</p>",
                          "posted_at": "2026-10-16T11:00:00Z"},
                         {"title": "Already sent", "posted_at": "2026-10-15T12:00:00Z"},
                         {"title": "Scheduled", "posted_at": "2026-10-17T12:00:00Z"}])
        return iter([
            {"name": "Overdue", "due_at": "2026-10-14T12:00:00Z"},
            {"name": "Submitted", "submission": {"workflow_state": "submitted"}},
            {"name": "Excused", "submission": {"excused": True}},
            {"name": "Missing zero", "submission": {"workflow_state": "graded", "missing": True}},
            {"name": "Unpublished", "published": False},
            {"name": "Closed", "due_at": "2026-10-17T18:00:00Z", "lock_at": "2026-10-15T00:00:00Z"},
            {"name": "Locked", "locked_for_user": True},
            {"name": "Not open yet", "unlock_at": "2026-10-17T00:00:00Z"},
            {"name": "Expires now", "due_at": "2026-10-16T12:00:00Z"},
            {"name": "Later", "due_at": "2027-01-01T12:00:00Z"},
            {"name": "Upcoming", "due_at": "2026-10-17T18:00:00Z"},
            {"name": "No deadline"},
        ])


class ReminderTests(unittest.TestCase):
    def test_digest_filters_and_localizes_actual_canvas_shapes(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        assignments, announcements = collect(FakeCanvas(), now, 14)
        self.assertEqual([a["title"] for a in assignments],
                         ["Upcoming", "Missing zero", "No deadline"])
        digest = render(assignments, announcements, now, ZoneInfo("America/Los_Angeles"), 14)
        self.assertNotIn("Overdue", digest)
        self.assertIn("17/10 às 11:00", digest)
        self.assertIn("Tomorrow & Friday", digest)
        self.assertNotIn("<p>", digest)
        self.assertEqual([a["title"] for a in announcements], ["Office hours"])

    def test_assignments_default_to_two_weeks(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        assignments, _ = collect(FakeCanvas(), now)
        self.assertNotIn("Later", [a["title"] for a in assignments])
        self.assertIn("Upcoming", [a["title"] for a in assignments])

    def test_two_week_boundary_is_inclusive(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        canvas = MagicMock()
        canvas.pages.side_effect = [[{"id": 42, "name": "CS"}],
                                    [{"name": "At boundary", "due_at": "2026-10-30T12:00:00Z"},
                                     {"name": "Beyond", "due_at": "2026-10-30T12:00:01Z"}], []]
        assignments, _ = collect(canvas, now)
        self.assertEqual([item["title"] for item in assignments], ["At boundary"])

    def test_digest_does_not_append_resource_urls(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        digest = render([{"course": "CS", "title": "Homework", "due": None,
                          "url": "https://bcourses.berkeley.edu/assignments/1"}],
                        [{"course": "CS", "title": "News", "text": "Office hours today",
                          "url": "https://bcourses.berkeley.edu/announcements/1"}],
                        now, ZoneInfo("America/Los_Angeles"))
        self.assertNotIn("https://", digest)
        self.assertIn("Homework", digest)
        self.assertIn("Office hours today", digest)

    @patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "123"})
    @patch("reminder.datetime")
    @patch("reminder.run")
    def test_cloud_schedule_respects_dst_and_does_not_repeat(self, run_mock, clock):
        # 15:00 UTC = 08:00 summer, but 07:00 winter in Berkeley.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            args = Namespace(channel="telegram")
            key = f"{delivery_key(args)}:America/Los_Angeles:08:00"
            argv = ["reminder.py", "--channel", "telegram", "--daily-at", "08:00",
                    "--scheduled-once", "--state", str(path)]
            for date, utc_hour, expected in [("2026-07-01", 15, True), ("2026-12-01", 15, False),
                                              ("2026-12-01", 16, True)]:
                utc = datetime.fromisoformat(f"{date}T{utc_hour}:00:00+00:00")
                clock.now.return_value = utc.astimezone(ZoneInfo("America/Los_Angeles"))
                run_mock.reset_mock()
                with patch("sys.argv", argv):
                    main()
                self.assertEqual(run_mock.called, expected)
            path.write_text(json.dumps({"daily": {key: "2026-12-01"}}))
            run_mock.reset_mock()
            with patch("sys.argv", argv):
                main()
            run_mock.assert_not_called()

    def test_announcements_use_exact_interval_even_after_missed_days(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        _, announcements = collect(FakeCanvas(), now, since=datetime(2026, 10, 10, tzinfo=timezone.utc))
        self.assertEqual([a["title"] for a in announcements], ["Office hours", "Already sent"])

    @patch.dict("os.environ", {"CANVAS_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
    @patch("reminder.send")
    @patch("reminder.collect", return_value=([], []))
    def test_successful_send_advances_watermark_but_failure_and_preview_do_not(self, collect_mock, send_mock):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            args = Namespace(state=str(path), channel="telegram", days=None, timezone="America/Los_Angeles")
            run(args, "daily-key", "2026-10-16")
            saved = path.read_text()
            state = json.loads(saved)
            watermark = datetime.fromisoformat(state["deliveries"][delivery_key(args)])
            self.assertEqual(state["daily"]["daily-key"], "2026-10-16")
            run(args)
            self.assertEqual(collect_mock.call_args.args[3], watermark)
            saved = path.read_text()
            send_mock.side_effect = ValueError("delivery failed")
            with self.assertRaises(ValueError):
                run(args)
            self.assertEqual(path.read_text(), saved)
            send_mock.side_effect = None
            args.channel = "console"
            run(args)
            self.assertEqual(path.read_text(), saved)
            self.assertEqual(collect_mock.call_args.args[3],
                             datetime.fromisoformat(json.loads(saved)["deliveries"][delivery_key(args, "telegram")]))

    @patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "123"})
    def test_destination_has_separate_watermark(self):
        args = Namespace(channel="telegram")
        original = delivery_key(args)
        with patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "456"}):
            self.assertNotEqual(original, delivery_key(args))

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

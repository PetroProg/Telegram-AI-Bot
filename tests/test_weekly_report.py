import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.config import Settings
from app.db import repository
from app.db.repository import UserPromptStat
from app.services.weekly_report import (
    compute_latest_report_window,
    compute_next_report_time,
    format_weekly_report,
    is_window_due,
    pluralize_prompts,
    send_weekly_report_if_due,
)


class WeeklyReportTests(unittest.IsolatedAsyncioTestCase):
    def test_pluralize_prompts(self):
        cases = {
            0: "промптов",
            1: "промпт",
            2: "промпта",
            4: "промпта",
            5: "промптов",
            11: "промптов",
            12: "промптов",
            14: "промптов",
            21: "промпт",
            22: "промпта",
            25: "промптов",
            101: "промпт",
            111: "промптов",
        }
        for count, expected in cases.items():
            with self.subTest(count=count):
                self.assertEqual(pluralize_prompts(count), expected)

    def test_window_sunday_exact_and_grace(self):
        tz = ZoneInfo("Europe/Zurich")

        # Sunday 2026-11-22 12:00 -> due now
        sun_noon = datetime(2026, 11, 22, 12, 0, tzinfo=tz)
        window = compute_latest_report_window(sun_noon, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(window.report_key, "2026-11-22")
        self.assertEqual(window.period_start_local, datetime(2026, 11, 15, 12, 0, tzinfo=tz))
        self.assertEqual(window.period_end_local, sun_noon)
        self.assertTrue(is_window_due(sun_noon, window))

        # Sunday 11:59 -> previous Sunday's window, not due
        sun_before = datetime(2026, 11, 22, 11, 59, tzinfo=tz)
        prev_window = compute_latest_report_window(sun_before, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(prev_window.report_key, "2026-11-15")
        self.assertFalse(is_window_due(sun_before, prev_window))

        # Sunday 16:30 -> inside 12h recovery window, still due if missed
        sun_later = datetime(2026, 11, 22, 16, 30, tzinfo=tz)
        same_window = compute_latest_report_window(sun_later, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(same_window.report_key, "2026-11-22")
        self.assertTrue(is_window_due(sun_later, same_window))

        # Monday 09:00 -> outside 12h grace window, should not fire on startup
        mon_morning = datetime(2026, 11, 23, 9, 0, tzinfo=tz)
        mon_window = compute_latest_report_window(mon_morning, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(mon_window.report_key, "2026-11-22")
        self.assertFalse(is_window_due(mon_morning, mon_window))

    def test_window_dst_transitions_zurich(self):
        tz = ZoneInfo("Europe/Zurich")

        # Spring forward: 2026-03-29 is DST start in Europe/Zurich (167h week)
        spring_sun = datetime(2026, 3, 29, 12, 0, tzinfo=tz)
        spring_win = compute_latest_report_window(spring_sun, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(spring_win.period_start_local.hour, 12)
        self.assertEqual(spring_win.period_end_local.hour, 12)
        self.assertEqual(spring_win.period_end_utc - spring_win.period_start_utc, timedelta(hours=167))

        # Fall back: 2026-10-25 is DST end in Europe/Zurich (169h week)
        fall_sun = datetime(2026, 10, 25, 12, 0, tzinfo=tz)
        fall_win = compute_latest_report_window(fall_sun, target_day=6, target_hour=12, target_minute=0)
        self.assertEqual(fall_win.period_start_local.hour, 12)
        self.assertEqual(fall_win.period_end_local.hour, 12)
        self.assertEqual(fall_win.period_end_utc - fall_win.period_start_utc, timedelta(hours=169))

    def test_compute_next_report_time(self):
        tz = ZoneInfo("Europe/Zurich")
        sun_before = datetime(2026, 11, 22, 11, 59, tzinfo=tz)
        self.assertEqual(
            compute_next_report_time(sun_before, 6, 12, 0),
            datetime(2026, 11, 22, 12, 0, tzinfo=tz),
        )
        sun_exact = datetime(2026, 11, 22, 12, 0, tzinfo=tz)
        self.assertEqual(
            compute_next_report_time(sun_exact, 6, 12, 0),
            datetime(2026, 11, 29, 12, 0, tzinfo=tz),
        )
        mon = datetime(2026, 11, 23, 20, 0, tzinfo=tz)
        self.assertEqual(
            compute_next_report_time(mon, 6, 12, 0),
            datetime(2026, 11, 29, 12, 0, tzinfo=tz),
        )

    def test_format_weekly_report_with_users_and_escaping(self):
        tz = ZoneInfo("Europe/Zurich")
        start = datetime(2026, 11, 15, 12, 0, tzinfo=tz)
        end = datetime(2026, 11, 22, 12, 0, tzinfo=tz)
        stats = [
            UserPromptStat(user_id=1, username="petroprog", first_name="Petro", total_prompts=42, photo_prompts=0),
            UserPromptStat(user_id=2, username="alice", first_name="Alice", total_prompts=15, photo_prompts=3),
            UserPromptStat(user_id=3, username=None, first_name="Bob <Admin>&Co", total_prompts=1, photo_prompts=0),
            UserPromptStat(user_id=4, username=None, first_name=None, total_prompts=2, photo_prompts=0),
        ]

        chunks = format_weekly_report(stats, start, end, "Europe/Zurich")
        self.assertEqual(len(chunks), 1)
        text = chunks[0]
        self.assertIn("1. @petroprog — <b>42</b> промпта", text)
        self.assertIn("2. @alice — <b>15</b> промптов (📸 фото: 3)", text)
        self.assertIn("3. Bob &lt;Admin&gt;&amp;Co (ID <code>3</code>) — <b>1</b> промпт", text)
        self.assertIn("4. ID <code>4</code> — <b>2</b> промпта", text)
        self.assertIn("Всего:</b> 60 промптов (пользователей: 4)", text)

    def test_format_weekly_report_empty(self):
        tz = ZoneInfo("Europe/Zurich")
        start = datetime(2026, 11, 15, 12, 0, tzinfo=tz)
        end = datetime(2026, 11, 22, 12, 0, tzinfo=tz)

        chunks = format_weekly_report([], start, end, "Europe/Zurich")
        self.assertEqual(len(chunks), 1)
        self.assertIn("промптов не было (0)", chunks[0])

    def test_format_weekly_report_splits_long_messages(self):
        tz = ZoneInfo("Europe/Zurich")
        start = datetime(2026, 11, 15, 12, 0, tzinfo=tz)
        end = datetime(2026, 11, 22, 12, 0, tzinfo=tz)
        stats = [
            UserPromptStat(user_id=i, username=f"user_{i:04d}", first_name=None, total_prompts=i, photo_prompts=0)
            for i in range(1, 200)
        ]

        chunks = format_weekly_report(stats, start, end, "Europe/Zurich", max_length=500)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 500)

    async def test_get_or_create_user_preserves_username_when_omitted(self):
        existing_user = SimpleNamespace(id=123, username="petroprog", first_name="Petro")
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = existing_user

        session = AsyncMock()
        session.execute.return_value = execute_result

        user = await repository.get_or_create_user(session, user_id=123)
        self.assertEqual(user.username, "petroprog")
        self.assertEqual(user.first_name, "Petro")
        session.commit.assert_not_called()

        user = await repository.get_or_create_user(session, user_id=123, username="new_nick")
        self.assertEqual(user.username, "new_nick")
        self.assertEqual(user.first_name, "Petro")
        session.commit.assert_awaited_once()

    def test_settings_validation(self):
        cfg = Settings(_env_file=None, REPORT_CHAT_ID="", ALLOWED_USER_IDS="111,222")
        self.assertIsNone(cfg.REPORT_CHAT_ID)
        self.assertEqual(cfg.effective_report_chat_id, 111)

        with self.assertRaises(ValidationError):
            Settings(_env_file=None, REPORT_TIMEZONE="Invalid/Zone")

    async def test_send_weekly_report_if_due_idempotency(self):
        tz = ZoneInfo("Europe/Zurich")
        sun_noon_utc = datetime(2026, 11, 22, 12, 0, tzinfo=tz).astimezone(timezone.utc)
        bot = AsyncMock()

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.weekly_report.settings") as mock_settings,
            patch("app.services.weekly_report.async_session_factory", return_value=mock_session_cm),
            patch("app.services.weekly_report.repository.has_weekly_report_run", new_callable=AsyncMock) as mock_has,
            patch("app.services.weekly_report.repository.get_prompt_stats", new_callable=AsyncMock) as mock_stats,
            patch("app.services.weekly_report.repository.record_weekly_report_run", new_callable=AsyncMock) as mock_rec,
        ):
            mock_settings.WEEKLY_REPORT_ENABLED = True
            mock_settings.effective_report_chat_id = 999
            mock_settings.REPORT_TIMEZONE = "Europe/Zurich"
            mock_settings.WEEKLY_REPORT_DAY = 6
            mock_settings.WEEKLY_REPORT_HOUR = 12
            mock_settings.WEEKLY_REPORT_MINUTE = 0

            # First run: not sent yet -> sends & records
            mock_has.return_value = False
            mock_stats.return_value = [
                UserPromptStat(user_id=999, username="petroprog", first_name="Petro", total_prompts=5, photo_prompts=1)
            ]
            sent = await send_weekly_report_if_due(bot, now_utc=sun_noon_utc)
            self.assertTrue(sent)
            bot.send_message.assert_awaited_once()
            mock_rec.assert_awaited_once()

            # Second run: already recorded -> does not resend
            bot.send_message.reset_mock()
            mock_rec.reset_mock()
            mock_has.return_value = True
            sent_again = await send_weekly_report_if_due(bot, now_utc=sun_noon_utc)
            self.assertFalse(sent_again)
            bot.send_message.assert_not_awaited()
            mock_rec.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

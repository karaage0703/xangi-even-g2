import unittest
from unittest.mock import patch

from bridge import even_g2_bridge


def make_detail(count: int) -> dict:
    return {
        "id": "session-1",
        "title": "Long thread",
        "platform": "discord",
        "messages": [
            {"id": str(index), "role": "user", "content": f"message {index}"}
            for index in range(count)
        ],
    }


class TerminalSessionDetailTest(unittest.TestCase):
    @patch.object(even_g2_bridge, "session_detail", return_value=make_detail(62))
    def test_returns_latest_window_by_default(self, _mock_detail):
        result = even_g2_bridge.terminal_session_detail("session-1", limit=30)

        self.assertEqual(result["start"], 32)
        self.assertEqual(result["end"], 62)
        self.assertEqual(result["totalMessages"], 62)
        self.assertTrue(result["hasOlder"])
        self.assertFalse(result["hasNewer"])
        self.assertEqual(result["messages"][0]["id"], "32")
        self.assertEqual(result["messages"][-1]["id"], "61")

    @patch.object(even_g2_bridge, "session_detail", return_value=make_detail(62))
    def test_returns_requested_window(self, _mock_detail):
        result = even_g2_bridge.terminal_session_detail("session-1", limit=30, start=0)

        self.assertEqual(result["start"], 0)
        self.assertEqual(result["end"], 30)
        self.assertFalse(result["hasOlder"])
        self.assertTrue(result["hasNewer"])
        self.assertEqual(result["messages"][0]["id"], "0")
        self.assertEqual(result["messages"][-1]["id"], "29")

    @patch.object(even_g2_bridge, "session_detail", return_value=make_detail(62))
    def test_returns_final_partial_window(self, _mock_detail):
        result = even_g2_bridge.terminal_session_detail("session-1", limit=30, start=60)

        self.assertEqual(result["start"], 60)
        self.assertEqual(result["end"], 62)
        self.assertEqual([message["id"] for message in result["messages"]], ["60", "61"])


class TerminalSessionListTest(unittest.TestCase):
    @patch.object(even_g2_bridge, "discord_channel_contexts", return_value={})
    @patch.object(even_g2_bridge, "session_latest_message", return_value=("", ""))
    @patch.object(even_g2_bridge, "request_json")
    def test_recent_idle_session_is_not_hidden_by_old_idle_session(
        self,
        mock_request_json,
        _mock_latest_message,
        _mock_discord_contexts,
    ):
        mock_request_json.return_value = {
            "sessions": [
                {
                    "id": "old-idle",
                    "title": "Old completed session",
                    "platform": "discord",
                    "updatedAt": "2026-07-25T15:49:35.040Z",
                    "isActive": False,
                },
                {
                    "id": "recent-idle",
                    "title": "Recent completed session",
                    "platform": "discord",
                    "updatedAt": "2026-07-27T05:50:27.099Z",
                    "isActive": False,
                },
            ]
        }

        result = even_g2_bridge.list_terminal_sessions(limit=12)

        ids = [session["id"] for session in result["sessions"]]
        self.assertEqual(ids, ["recent-idle", "old-idle"])

    @patch.object(even_g2_bridge, "discord_channel_contexts", return_value={})
    @patch.object(even_g2_bridge, "session_latest_message", return_value=("", ""))
    @patch.object(even_g2_bridge, "request_json")
    def test_active_turn_is_busy(
        self,
        mock_request_json,
        _mock_latest_message,
        _mock_discord_contexts,
    ):
        mock_request_json.return_value = {
            "sessions": [
                {
                    "id": "active-turn",
                    "title": "Running session",
                    "platform": "discord",
                    "updatedAt": "2026-07-27T06:37:54.071Z",
                    "isActive": True,
                }
            ]
        }

        result = even_g2_bridge.list_terminal_sessions(limit=12)

        self.assertEqual(result["sessions"][0]["status"], "busy")
        self.assertTrue(result["sessions"][0]["isActive"])

    @patch.object(even_g2_bridge, "discord_channel_contexts", return_value={})
    @patch.object(even_g2_bridge, "session_latest_message", return_value=("", ""))
    @patch.object(even_g2_bridge, "request_json")
    def test_inactive_session_is_idle_even_with_future_timeout(
        self,
        mock_request_json,
        _mock_latest_message,
        _mock_discord_contexts,
    ):
        mock_request_json.return_value = {
            "sessions": [
                {
                    "id": "completed-turn",
                    "title": "Completed session",
                    "platform": "discord",
                    "updatedAt": "2026-07-27T06:37:54.071Z",
                    "isActive": False,
                    "timeoutAt": 9_999_999_999_999,
                }
            ]
        }

        result = even_g2_bridge.list_terminal_sessions(limit=12)

        self.assertEqual(result["sessions"][0]["status"], "idle")
        self.assertFalse(result["sessions"][0]["isActive"])

    @patch.object(even_g2_bridge.time, "time", return_value=1_000)
    @patch.object(even_g2_bridge, "discord_channel_contexts", return_value={})
    @patch.object(even_g2_bridge, "session_latest_message", return_value=("", ""))
    @patch.object(even_g2_bridge, "request_json")
    def test_invalid_and_expired_timeouts_are_idle(
        self,
        mock_request_json,
        _mock_latest_message,
        _mock_discord_contexts,
        _mock_time,
    ):
        mock_request_json.return_value = {
            "sessions": [
                {
                    "id": f"invalid-{index}",
                    "title": f"Invalid timeout {value}",
                    "platform": "discord",
                    "updatedAt": f"2026-07-27T06:37:5{index}.071Z",
                    "timeoutAt": value,
                }
                for index, value in enumerate(("0", "not-a-time", "Infinity", 999_000))
            ]
        }

        result = even_g2_bridge.list_terminal_sessions(limit=12)

        self.assertTrue(all(session["status"] == "idle" for session in result["sessions"]))
        self.assertTrue(all(not session["isActive"] for session in result["sessions"]))
        self.assertTrue(all(session["remainingSec"] == 0 for session in result["sessions"]))

    @patch.object(even_g2_bridge, "discord_channel_contexts", return_value={})
    @patch.object(even_g2_bridge, "session_latest_message", return_value=("", ""))
    @patch.object(even_g2_bridge, "request_json")
    def test_recent_web_session_is_not_hidden_by_discord_priority(
        self,
        mock_request_json,
        _mock_latest_message,
        _mock_discord_contexts,
    ):
        old_discord_sessions = [
            {
                "id": f"discord-{index}",
                "title": f"Discord {index}",
                "platform": "discord",
                "updatedAt": f"2026-07-18T{index:02d}:00:00.000Z",
            }
            for index in range(12)
        ]
        mock_request_json.return_value = {
            "sessions": [
                *old_discord_sessions,
                {
                    "id": "new-web-session",
                    "title": "Even G2 Terminal",
                    "platform": "web",
                    "updatedAt": "2026-07-19T04:54:39.615Z",
                },
            ]
        }

        result = even_g2_bridge.list_terminal_sessions(limit=12)

        ids = [session["id"] for session in result["sessions"]]
        self.assertEqual(ids[0], "new-web-session")
        self.assertIn("new-web-session", ids)


class TerminalCandidateTest(unittest.TestCase):
    @patch.object(even_g2_bridge, "terminal_session_detail")
    def test_returns_only_stored_ai_candidates(self, mock_detail):
        mock_detail.return_value = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "answer",
                    "replySuggestions": ["続けて", "詳しく教えて"],
                }
            ]
        }

        result = even_g2_bridge.generate_terminal_candidates({"session_id": "session-1"})

        self.assertEqual(
            result["candidates"],
            [{"text": "続けて"}, {"text": "詳しく教えて"}],
        )

    @patch.object(even_g2_bridge, "terminal_session_detail")
    def test_does_not_add_fixed_candidates(self, mock_detail):
        mock_detail.return_value = {
            "messages": [{"role": "assistant", "content": "answer"}]
        }

        result = even_g2_bridge.generate_terminal_candidates({"session_id": "session-1"})

        self.assertEqual(result["candidates"], [])

    @patch.object(even_g2_bridge, "terminal_session_detail")
    def test_does_not_reuse_candidates_after_a_new_user_message(self, mock_detail):
        mock_detail.return_value = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "answer",
                    "replySuggestions": ["古い候補"],
                },
                {"role": "user", "content": "new question"},
            ]
        }

        result = even_g2_bridge.generate_terminal_candidates({"session_id": "session-1"})

        self.assertEqual(result["candidates"], [])


class DiscordReplyTest(unittest.TestCase):
    @patch.object(even_g2_bridge, "discord_request")
    def test_adds_and_removes_processing_reaction(self, mock_discord_request):
        even_g2_bridge.discord_add_reaction(
            "123456789012345678",
            "123456789012345679",
            "👀",
        )
        even_g2_bridge.discord_remove_reaction(
            "123456789012345678",
            "123456789012345679",
            "👀",
        )

        path = (
            "/channels/123456789012345678/messages/123456789012345679"
            "/reactions/%F0%9F%91%80/@me"
        )
        self.assertEqual(
            mock_discord_request.call_args_list,
            [
                unittest.mock.call("PUT", path),
                unittest.mock.call("DELETE", path),
            ],
        )

    @patch.object(even_g2_bridge, "discord_add_reaction")
    @patch.object(even_g2_bridge.threading, "Thread")
    @patch.object(even_g2_bridge, "discord_send_message")
    @patch.object(even_g2_bridge, "terminal_session_summary")
    def test_adds_processing_reaction_before_starting_worker(
        self,
        mock_summary,
        mock_send,
        mock_thread,
        mock_add_reaction,
    ):
        mock_summary.return_value = {
            "id": "session-1",
            "platform": "discord",
            "contextKey": "123456789012345678",
        }
        mock_send.return_value = {"id": "123456789012345679"}

        result = even_g2_bridge.post_terminal_session_message(
            {"session_id": "session-1", "text": "長い作業をして"}
        )

        mock_send.assert_called_once_with(
            "123456789012345678",
            "G2 User: 長い作業をして",
        )
        mock_add_reaction.assert_called_once_with(
            "123456789012345678",
            "123456789012345679",
            "👀",
        )
        mock_thread.assert_called_once_with(
            target=even_g2_bridge.discord_reply_worker,
            args=(
                result["reply_job_id"],
                "123456789012345678",
                "長い作業をして",
                "123456789012345679",
                "👀",
            ),
            daemon=True,
        )
        mock_thread.return_value.start.assert_called_once_with()

    @patch.object(even_g2_bridge, "set_reply_job")
    @patch.object(even_g2_bridge, "discord_remove_reaction")
    @patch.object(even_g2_bridge, "discord_send_message")
    @patch.object(even_g2_bridge, "ask_xangi_with_retry", return_value="完了しました")
    def test_worker_removes_reaction_after_posting_final_reply(
        self,
        _mock_ask,
        mock_send,
        mock_remove_reaction,
        mock_set_job,
    ):
        mock_send.return_value = {"id": "123456789012345680"}

        even_g2_bridge.discord_reply_worker(
            "job-1",
            "123456789012345678",
            "長い作業をして",
            "123456789012345679",
            "👀",
        )

        mock_send.assert_called_once_with(
            "123456789012345678",
            "完了しました",
            reply_to_message_id="123456789012345679",
        )
        mock_remove_reaction.assert_called_once_with(
            "123456789012345678",
            "123456789012345679",
            "👀",
        )
        self.assertEqual(mock_set_job.call_args_list[0], unittest.mock.call("job-1", status="running"))
        self.assertEqual(mock_set_job.call_args_list[-1].kwargs["status"], "done")


if __name__ == "__main__":
    unittest.main()

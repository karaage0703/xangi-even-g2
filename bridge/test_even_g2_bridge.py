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


if __name__ == "__main__":
    unittest.main()

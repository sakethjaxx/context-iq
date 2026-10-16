import importlib
import unittest
from unittest import mock

from tests.helpers import ConfigDirTestCase, assistant
import claude_code as cc

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False

import mcp_server  # imports `mcp` lazily, so this works without the package


class McpToolLogicTest(ConfigDirTestCase):
    def setUp(self):
        super().setUp()
        importlib.reload(mcp_server)

    def test_exact_numbers_in_claude_code(self):
        self.transcript([assistant(cache_read=120_000)], session="live", project=cc.project_key("/repo"))
        with mock.patch("os.getcwd", return_value="/repo"):
            health = mcp_server.context_health()
            self.assertEqual((health["source"], health["live_context_tokens"]), ("claude-code (exact)", 120_000))
            self.assertFalse(mcp_server.track_turn(1, 1)["tracked"])

    def test_estimates_elsewhere(self):
        with mock.patch("os.getcwd", return_value="/desktop"):
            self.assertEqual(mcp_server.context_health()["status"], "unknown")
            self.assertTrue(mcp_server.track_turn(150_000, 2_000, model="claude-haiku-4-5")["tracked"])
            health = mcp_server.context_health()
            self.assertEqual(health["source"], "estimated (track_turn)")
            self.assertEqual(health["live_context_tokens"], 152_000)
            mcp_server.reset_session()
            self.assertEqual(mcp_server.session_stats()["turns"], 0)


@unittest.skipUnless(HAVE_MCP, "mcp package not installed")
class McpServerTest(unittest.TestCase):
    def test_registers_tools(self):
        import asyncio
        server = mcp_server.build_server()
        names = {t.name for t in asyncio.run(server.list_tools())}
        self.assertEqual(names, {"get_context_pressure_score", "get_session_stats", "track_turn", "reset_session"})


if __name__ == "__main__":
    unittest.main()

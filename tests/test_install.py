import contextlib
import io
import json
import os
import unittest
from unittest import mock

from tests.helpers import ROOT, ConfigDirTestCase
import install


def run(*args):
    out = io.StringIO()
    with mock.patch("install.shutil.which", return_value=None), contextlib.redirect_stdout(out):
        code = install.main(list(args))
    return code, out.getvalue()


class InstallTest(ConfigDirTestCase):
    def setUp(self):
        super().setUp()
        self.settings = os.path.join(self.config, "settings.json")

    def write(self, data):
        with open(self.settings, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read(self):
        with open(self.settings, encoding="utf-8") as fh:
            return json.load(fh)

    def our_hooks(self, data):
        return [h for g in data.get("hooks", {}).get("Stop", []) for h in g["hooks"] if install.is_our_hook(h["command"])]

    def backups(self):
        return [f for f in os.listdir(self.config) if ".bak-contextiq-" in f]

    def test_fresh_install(self):
        code, _ = run()
        self.assertEqual(code, 0)
        data = self.read()
        self.assertIn("statusline.py", data["statusLine"]["command"])
        self.assertEqual(len(self.our_hooks(data)), 1)
        self.assertTrue(os.path.exists(install.skill_path()))

    def test_preserves_unrelated_settings_and_is_idempotent(self):
        original = {"model": "opus", "env": {"NAME": "bär"},
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "~/mine.sh"}]}],
                              "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}
        self.write(original)
        run()
        run()
        data = self.read()
        self.assertEqual((data["model"], data["env"]), ("opus", {"NAME": "bär"}))
        self.assertEqual(data["hooks"]["PreToolUse"], original["hooks"]["PreToolUse"])
        self.assertEqual(data["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
        self.assertEqual(len(self.our_hooks(data)), 1)
        self.assertEqual(len(self.backups()), 1)  # second run changed nothing

    def test_keeps_foreign_status_line_unless_forced(self):
        self.write({"statusLine": {"type": "command", "command": "~/.claude/statusline.sh", "padding": 1}})
        _, out = run()
        self.assertEqual(self.read()["statusLine"]["command"], "~/.claude/statusline.sh")
        self.assertIn("--force", out)
        run("--force")
        line = self.read()["statusLine"]
        self.assertIn("statusline.py", line["command"])
        self.assertEqual(line["padding"], 1)

    def test_upgrades_legacy_install(self):
        self.write({"statusLine": {"type": "command", "command": "python C:\\Users\\me\\context-iq\\statusline.py",
                                   "refreshInterval": 10},
                    "permissions": {"allow": ["mcp__context-iq__*"]}})
        run()
        line = self.read()["statusLine"]
        self.assertNotIn("refreshInterval", line)
        self.assertIn(install.shell_path(ROOT), line["command"])

    def test_uninstall_removes_only_ours(self):
        self.write({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "~/mine.sh"}]}]},
                    "permissions": {"allow": ["Bash(ls:*)", "mcp__context-iq__*"]}})
        run()
        run("--uninstall")
        data = self.read()
        self.assertNotIn("statusLine", data)
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "~/mine.sh"}]}])
        self.assertEqual(data["permissions"]["allow"], ["Bash(ls:*)"])
        self.assertFalse(os.path.exists(install.skill_path()))

    def test_uninstall_leaves_foreign_status_line(self):
        self.write({"statusLine": {"type": "command", "command": "~/.claude/statusline.sh"}})
        run("--uninstall")
        self.assertEqual(self.read()["statusLine"]["command"], "~/.claude/statusline.sh")

    def test_invalid_json_is_never_overwritten(self):
        with open(self.settings, "w") as fh:
            fh.write('{"a": 1,')
        code, out = run()
        self.assertEqual(code, 1)
        with open(self.settings) as fh:
            self.assertEqual(fh.read(), '{"a": 1,')
        self.assertIn("nothing was changed", out)

    def test_dry_run_writes_nothing(self):
        code, out = run("--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.settings))
        self.assertFalse(os.path.exists(install.skill_path()))
        self.assertIn("would write", out)

    def test_plugin_users_get_no_duplicate_hook(self):
        self.write({"enabledPlugins": {"context-iq@context-iq": True}})
        run()
        data = self.read()
        self.assertEqual(self.our_hooks(data), [])
        self.assertIn("statusLine", data)
        self.assertFalse(os.path.exists(install.skill_path()))

    def test_statusline_only_copy(self):
        run("--statusline-only", "--copy")
        runtime = os.path.join(self.config, "context-iq", "runtime")
        self.assertEqual(sorted(os.listdir(runtime)), sorted(install.RUNTIME_FILES))
        data = self.read()
        self.assertIn(install.shell_path(runtime), data["statusLine"]["command"])
        self.assertNotIn("hooks", data)


class HelpersTest(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(install.quote("/usr/bin/python3"), "/usr/bin/python3")
        quoted = install.quote("/Users/Jane Doe/context-iq/statusline.py")
        self.assertIn("Jane Doe", quoted)
        self.assertIn(quoted[0], "\"'")

    def test_ownership(self):
        self.assertTrue(install.is_our_hook('/usr/bin/python3 "/a b/contextiq.py" hook'))
        self.assertFalse(install.is_our_hook("python3 contextiq.py health"))
        self.assertTrue(install.is_our_statusline("python /home/me/context-iq/statusline.py", ()))
        self.assertTrue(install.is_our_statusline("python /opt/ciq/statusline.py", ("/opt/ciq",)))
        self.assertFalse(install.is_our_statusline("~/.claude/statusline.py", ("/opt/ciq",)))

    def test_skill_template_renders_absolute_command(self):
        text = install.render_skill("/usr/bin/python3", "/opt/ciq")
        self.assertIn("/usr/bin/python3 /opt/ciq/contextiq.py health", text)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", text)
        self.assertIn("${CLAUDE_SESSION_ID}", text)


if __name__ == "__main__":
    unittest.main()

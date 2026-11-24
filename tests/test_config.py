import os
import stat
import tempfile
import unittest
from unittest import mock

import ets_server_entrypoint as ep


class TestSiiEscape(unittest.TestCase):

    def test_plain_value_unchanged(self):
        self.assertEqual(ep.sii_escape("My Server 123"), "My Server 123")

    def test_quotes_and_backslashes_escaped(self):
        self.assertEqual(ep.sii_escape('Tim\'s "Convoy"'), 'Tim\'s \\"Convoy\\"')
        self.assertEqual(ep.sii_escape("a\\b"), "a\\\\b")

    def test_control_characters_removed(self):
        self.assertEqual(ep.sii_escape("line1\nline2\r\t"), "line1line2")

    def test_unicode_kept(self):
        self.assertEqual(ep.sii_escape("Grüße äöü"), "Grüße äöü")


class TestGenerateConfig(unittest.TestCase):

    def test_injection_via_name_not_possible(self):
        env = {"ETS_SERVER_NAME": 'x"\n password: "hacked'}
        with mock.patch.dict(os.environ, env, clear=False):
            config = ep.generate_config()
        lobby_lines = [l for l in config.splitlines() if "lobby_name" in l]
        self.assertEqual(len(lobby_lines), 1)
        self.assertEqual(lobby_lines[0], ' lobby_name: "x\\" password: \\"hacked"')
        password_lines = [l for l in config.splitlines() if l.strip().startswith("password:")]
        self.assertEqual(password_lines, [' password: ""'])


class TestModeratorList(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(ep.generate_moderator_list([""]), "moderator_list: 0")

    def test_whitespace_and_trailing_comma(self):
        out = ep.generate_moderator_list(" 123, 456 ,".split(","))
        self.assertEqual(out, "moderator_list: 2\n moderator_list[0]: 123\n moderator_list[1]: 456\n")

    def test_invalid_ids_dropped(self):
        out = ep.generate_moderator_list(["123", "abc\n evil: 1"])
        self.assertEqual(out, "moderator_list: 1\n moderator_list[0]: 123\n")


class TestMaxPlayerWorkaround(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "config_ds.cfg")

    def tearDown(self):
        if os.path.exists(self.cfg):
            os.chmod(self.cfg, 0o600)
        self.tmp.cleanup()

    def write(self, content):
        with open(self.cfg, "w") as f:
            f.write(content)

    def test_get_current_missing_file(self):
        self.assertEqual(ep.get_current_max_players(self.cfg), 0)

    def test_get_current_finds_correct_line(self):
        self.write('uset g_foo "3"\nuset g_max_convoy_size "16"\nuset g_bar "5"\n')
        self.assertEqual(ep.get_current_max_players(self.cfg), 16)

    def test_get_current_setting_missing(self):
        self.write('uset g_foo "abc"\n')
        self.assertEqual(ep.get_current_max_players(self.cfg), 0)

    def test_workaround_missing_file_does_not_crash(self):
        ep.max_player_workaround(self.cfg, 16)
        self.assertFalse(os.path.exists(self.cfg))

    def test_workaround_updates_value(self):
        self.write('uset g_foo "3"\nuset g_max_convoy_size "8"\n')
        ep.max_player_workaround(self.cfg, 32)
        self.assertEqual(ep.get_current_max_players(self.cfg), 32)
        with open(self.cfg) as f:
            self.assertIn('uset g_foo "3"', f.read())
        self.assertEqual(stat.S_IMODE(os.stat(self.cfg).st_mode), 0o400)


if __name__ == "__main__":
    unittest.main()

import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from wakeup import (
    ENDPOINT,
    PAIR_ENDPOINT,
    WakeupServer,
    find_tailscale_ipv4,
    load_settings,
    save_settings,
)


class WakeupProtocolTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.server = WakeupServer(("127.0.0.1", 0), "test-token", lambda: self.actions.append(True))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}{ENDPOINT}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_valid_token_runs_action(self):
        request = urllib.request.Request(
            self.url,
            data=b"",
            headers={"Authorization": "Bearer test-token"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.actions, [True])

    def test_invalid_token_does_not_run_action(self):
        request = urllib.request.Request(
            self.url,
            data=b"",
            headers={"Authorization": "Bearer wrong-token"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        self.assertEqual(self.actions, [])

    def test_other_path_does_not_run_action(self):
        request = urllib.request.Request(
            self.url + "/other",
            data=b"",
            headers={"Authorization": "Bearer test-token"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()
        self.assertEqual(self.actions, [])

    def test_pairing_code_is_checked_without_running_action(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{PAIR_ENDPOINT}",
            headers={"Authorization": "Bearer test-token"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.actions, [])

    def test_invalid_pairing_code_is_rejected(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{PAIR_ENDPOINT}",
            headers={"Authorization": "Bearer wrong-token"},
            method="GET",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        self.assertEqual(self.actions, [])


class SettingsTests(unittest.TestCase):
    def test_settings_are_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sender.json"
            expected = {"host": "192.0.2.1", "port": 8765, "token": "paired"}

            save_settings(path, expected)

            self.assertEqual(load_settings(path), expected)

    def test_missing_settings_are_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_settings(Path(directory) / "missing.json"), {})


class TailscaleAddressTests(unittest.TestCase):
    def test_selects_tailscale_ipv4(self):
        output = "fd7a:115c:a1e0::1\n192.168.1.20\n100.101.22.33\n"
        self.assertEqual(find_tailscale_ipv4(output), "100.101.22.33")

    def test_returns_none_without_tailscale_address(self):
        self.assertIsNone(find_tailscale_ipv4("192.168.1.20\n8.8.8.8\n"))


if __name__ == "__main__":
    unittest.main()

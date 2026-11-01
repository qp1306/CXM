"""Regression checks for the CXM installer (stdlib unittest)."""
import importlib.util
from pathlib import Path
import errno
import os
from unittest import TestCase, main
from unittest.mock import patch
import tempfile


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "cxm_manager.py"
spec = importlib.util.spec_from_file_location("cxm_manager", MODULE)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class SafeWriteTests(TestCase):
    def test_local_config_write_uses_destination_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "moonraker.conf"
            target.write_text("original\n", encoding="utf-8")
            old_replace = os.replace
            seen = []

            def guarded_replace(source, destination):
                source = Path(source)
                destination = Path(destination)
                seen.append(source)
                if source.parent.resolve() != destination.parent.resolve():
                    raise OSError(errno.EXDEV, "Invalid cross-device link")
                return old_replace(source, destination)

            with patch.object(manager.os, "replace", side_effect=guarded_replace):
                manager.save(target, "new configuration\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "new configuration\n")
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].parent.resolve(), target.parent.resolve())
            self.assertFalse(list(target.parent.glob(".moonraker.conf.cxm-*")))

    def test_privileged_snippet_write_copies_using_install(self):
        with patch.object(manager, "run") as mocked:
            manager.save(Path("/etc/nginx/snippets/cxm.conf"), "test", privileged=True)
            args = mocked.call_args.args
            self.assertEqual(args[:4], ("sudo", "install", "-m", "644"))
            self.assertEqual(args[-1], Path("/etc/nginx/snippets/cxm.conf"))


if __name__ == "__main__":
    main()

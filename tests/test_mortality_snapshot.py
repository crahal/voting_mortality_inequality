import contextlib
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class MortalitySnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(contextlib.chdir(self.root))
        self.data = b"original ASMR workbook bytes"
        self.spec = {
            "path": "data/raw/mortality/original.xlsx",
            "snapshot_path": "data/raw/mortality/snapshots/asmr_20261025T083750Z.xlsx",
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "size": len(self.data),
            "download": "https://example.test/asmr.xlsx",
        }
        self.original = self.root / self.spec["path"]
        self.snapshot = self.root / self.spec["snapshot_path"]
        self.original.parent.mkdir(parents=True)
        self.original.write_bytes(self.data)
        for target, value in [("PROJECT_ROOT", self.root), ("RAW_DATA_SOURCES", [self.spec])]:
            patcher = patch.object(helpers, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_archives_existing_bytes_and_always_reuses_same_path(self):
        with patch.object(helpers, "_fetch_mortality_download") as fetch:
            path = helpers.ensure_mortality_snapshot(download=False, check_remote=False)
            self.original.write_bytes(b"subsequent change to legacy file")
            self.assertEqual(helpers.mortality_data_path(), path)
        fetch.assert_not_called()
        self.assertEqual(path, self.snapshot)
        self.assertEqual(path.read_bytes(), self.data)

    def test_checks_remote_on_each_explicit_startup_call(self):
        with patch.object(helpers, "_fetch_mortality_download", return_value=self.data) as fetch:
            helpers.ensure_mortality_snapshot()
            helpers.ensure_mortality_snapshot()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(self.snapshot.read_bytes(), self.data)

    def test_changed_remote_warns_and_keeps_original_snapshot(self):
        changed = b"new workbook version"
        with patch.object(helpers, "_fetch_mortality_download", return_value=changed):
            with self.assertWarnsRegex(RuntimeWarning, "ONS ASMR download has changed") as warning:
                path = helpers.ensure_mortality_snapshot()
        self.assertIn(hashlib.sha256(changed).hexdigest(), str(warning.warning))
        self.assertIn(self.spec["sha256"], str(warning.warning))
        self.assertIn(os.path.relpath(self.snapshot), str(warning.warning))
        self.assertNotIn(str(self.root), str(warning.warning))
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(self.original.read_bytes(), self.data)

    def test_offline_failure_warns_and_keeps_verified_snapshot(self):
        with patch.object(helpers, "_fetch_mortality_download", side_effect=helpers.requests.ConnectionError("offline")):
            with self.assertWarnsRegex(RuntimeWarning, "upstream changes are unknown") as warning:
                path = helpers.ensure_mortality_snapshot()
        self.assertIn(os.path.relpath(self.snapshot), str(warning.warning))
        self.assertNotIn(str(self.root), str(warning.warning))
        self.assertEqual(path.read_bytes(), self.data)

    def test_first_download_is_verified_and_not_fetched_twice(self):
        self.original.unlink()
        with patch.object(helpers, "_fetch_mortality_download", return_value=self.data) as fetch:
            path = helpers.ensure_mortality_snapshot()
        fetch.assert_called_once_with(self.spec["download"])
        self.assertEqual(path.read_bytes(), self.data)

    def test_changed_first_download_cannot_become_analysis_snapshot(self):
        self.original.unlink()
        with patch.object(helpers, "_fetch_mortality_download", return_value=b"x" * len(self.data)):
            with self.assertRaisesRegex(ValueError, "sha256"):
                helpers.ensure_mortality_snapshot()
        self.assertFalse(self.snapshot.exists())
        self.assertEqual(list(self.snapshot.parent.iterdir()), [])

    def test_corrupt_snapshot_stops_before_remote_check(self):
        helpers.ensure_mortality_snapshot(check_remote=False)
        self.snapshot.write_bytes(b"x" * len(self.data))
        with patch.object(helpers, "_fetch_mortality_download") as fetch:
            with self.assertRaisesRegex(ValueError, "sha256"):
                helpers.ensure_mortality_snapshot()
        fetch.assert_not_called()

    def test_missing_snapshot_offline_stops_without_network(self):
        self.original.unlink()
        with patch.object(helpers, "_fetch_mortality_download") as fetch:
            with self.assertRaises(FileNotFoundError) as caught:
                helpers.ensure_mortality_snapshot(download=False, check_remote=False)
        self.assertIn(os.path.relpath(self.snapshot), str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))
        fetch.assert_not_called()

    def test_file_validation_errors_use_relative_paths(self):
        for contents, error_type, message in [
            (None, FileNotFoundError, "Missing required data file"),
            (b"", ValueError, "has size"),
            (b"x" * len(self.data), ValueError, "has sha256"),
        ]:
            with self.subTest(message=message):
                if contents is None:
                    self.original.unlink()
                else:
                    self.original.write_bytes(contents)
                with self.assertRaisesRegex(error_type, message) as caught:
                    helpers._verify_file(self.original, self.spec["sha256"], self.spec["size"])
                self.assertIn(os.path.relpath(self.original), str(caught.exception))
                self.assertNotIn(str(self.root), str(caught.exception))

    def test_raw_verification_uses_snapshot_even_when_legacy_file_changes(self):
        helpers.ensure_mortality_snapshot(check_remote=False)
        self.original.write_bytes(b"legacy changed")
        with patch.object(helpers, "RAW_DATA_SOURCE_EXTRA_FILES", {}):
            with patch.object(helpers, "validate_raw_data_schema"):
                helpers.ensure_raw_data(download=False)

    def test_source_markdown_links_to_snapshot(self):
        markdown = helpers.raw_data_sources_markdown(include_shapefile_components=False)
        self.assertIn(f"](../{self.spec['snapshot_path']})", markdown)
        self.assertIn(self.spec["sha256"], markdown)

    def test_remote_request_has_finite_timeout(self):
        with patch.object(helpers.requests, "get") as get:
            get.return_value.__enter__.return_value.content = self.data
            self.assertEqual(helpers._fetch_mortality_download(self.spec["download"]), self.data)
        self.assertEqual(get.call_args.kwargs["timeout"], 30)
        get.return_value.__enter__.return_value.raise_for_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()

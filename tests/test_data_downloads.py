import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nbformat
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import helpers
from boundary_sources import BOUNDARIES, encode_original_dbf
from election_sources import ELECTION_SOURCES, read_election_results


class DownloadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch.object(helpers, 'PROJECT_ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def spec(self, data):
        return {'path': 'data/test.csv', 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'download': 'https://example.test/data'}

    def test_requests_only_with_timeout_and_status_check(self):
        with patch.object(requests, 'get') as get:
            response = get.return_value.__enter__.return_value
            response.content = b'original'
            helpers._download_raw_file('https://example.test/data', self.root / 'file')
            self.assertEqual((self.root / 'file').read_bytes(), b'original')
            response.raise_for_status.assert_called_once()
            self.assertEqual(get.call_args.kwargs['timeout'], 120)

    def test_http_error_is_not_saved(self):
        with patch.object(requests, 'get') as get:
            get.return_value.__enter__.return_value.raise_for_status.side_effect = requests.HTTPError('403')
            with self.assertRaisesRegex(RuntimeError, '403'):
                helpers._download_raw_file('https://example.test/data', self.root / 'file')
        self.assertFalse((self.root / 'file').exists())

    def test_bad_hash_never_published_and_staging_removed(self):
        spec = self.spec(b'original')
        with patch.object(helpers, '_download_raw_file', side_effect=lambda url, path: path.write_bytes(b'changed!')):
            with self.assertRaisesRegex(ValueError, 'sha256'):
                helpers._fetch_pinned_source(spec)
        self.assertEqual(list((self.root / 'data').iterdir()), [])

    def test_existing_invalid_file_is_not_overwritten(self):
        spec = self.spec(b'original')
        path = self.root / spec['path']
        path.parent.mkdir()
        path.write_bytes(b'changed!')
        with patch.object(helpers, '_download_raw_file', side_effect=lambda url, path: path.write_bytes(b'original')):
            with self.assertRaises(ValueError):
                helpers._fetch_pinned_source(spec)
        self.assertEqual(path.read_bytes(), b'changed!')

    def test_csv_normalization_preserves_original_serialization(self):
        original = b'code,score\nA,1.0\nB,1.5\n'
        spec = dict(self.spec(original), normalize_csv=True)
        with patch.object(helpers, '_download_raw_file', side_effect=lambda url, path: path.write_bytes(b'code,score\r\nA,1\r\nB,1.5\r\n')):
            helpers._fetch_pinned_source(spec)
        self.assertEqual((self.root / spec['path']).read_bytes(), original)

    def test_every_required_source_has_a_download_recipe(self):
        self.assertTrue(all(spec.get('download') for spec in helpers.RAW_DATA_SOURCES))
        self.assertFalse(any('life_expectancy' in spec['path'] for spec in helpers.RAW_DATA_SOURCES))

    def test_missing_boundary_companion_triggers_bundle_fetch(self):
        spec = dict(self.spec(b'original'), path='data/boundary.shp', boundary_year=2019)
        (self.root / 'data').mkdir()
        (self.root / spec['path']).write_bytes(b'original')
        with patch.object(helpers, 'RAW_DATA_SOURCES', [spec]), \
                patch.object(helpers, 'RAW_DATA_SOURCE_EXTRA_FILES', {'data/boundary.dbf': ('hash', 1)}), \
                patch.object(helpers, '_fetch_pinned_source') as fetch:
            helpers.ensure_raw_data(verify=False)
        fetch.assert_called_once_with(spec)

    def test_notebook_fetches_before_loading_and_has_no_temporal_section(self):
        notebook = nbformat.read(ROOT / 'src/analysis.ipynb', as_version=4)
        codes = '\n'.join(cell.source for cell in notebook.cells if cell.cell_type == 'code')
        self.assertLess(codes.index('ensure_raw_data()'), codes.index('make_merged(2019)'))
        self.assertNotIn('make_sii', codes)
        self.assertNotIn('plot_over_time', codes)


class SourceIdentityTests(unittest.TestCase):
    def test_election_bytes_checked_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for year, spec in ELECTION_SOURCES.items():
                path = root / spec['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'pinned original'):
                    read_election_results(root, year)

    def test_election_table_hash_is_independent_of_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = ELECTION_SOURCES[2024]
            path = root / spec['path']
            path.parent.mkdir(parents=True)
            frame = pd.DataFrame({'ONS ID': [f'E{i}' for i in range(650)],
                                  'County name': '', 'Declaration time': '', 'Electorate': 1})
            data = frame.to_csv(index=False).encode()
            path.write_bytes(data)
            with patch.dict(spec, size=len(data), sha256=hashlib.sha256(data).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'original Excel analysis inputs'):
                    read_election_results(root, 2024)

    def test_dbf_schema_formatting_and_overflow_checks(self):
        for year in (2019, 2024):
            row = {name: 'A' if kind == 'C' else 1 for name, kind, _, _ in BOUNDARIES[year]['fields']}
            row['GlobalID'] = '{ABCDEF}'
            data = encode_original_dbf(pd.DataFrame([row]), year)
            count, header, record = struct.unpack('<IHH', data[4:12])
            self.assertEqual(count, 1)
            self.assertEqual(len(data), header + record + 1)
            self.assertIn(b'abcdef', data)
            self.assertNotIn(b'{ABCDEF}', data)
            self.assertIn(b'1.00000e+00' if year == 2024 else b'1.00000000000e+00', data)
            name = BOUNDARIES[year]['fields'][0][0]
            row[name] = 'X' * 100
            with self.assertRaisesRegex(ValueError, 'width'):
                encode_original_dbf(pd.DataFrame([row]), year)


if __name__ == '__main__':
    unittest.main()

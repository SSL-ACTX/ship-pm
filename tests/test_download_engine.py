"""Tests for ship.net.engine and multi-stream parallel resumable downloads."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ship.net.download import calc_sha256, fetch_cached_file
from ship.net.engine import DownloadEngine, DownloadMetadata, SegmentInfo


class TestDownloadEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_metadata_serialization(self):
        meta = DownloadMetadata(
            url="https://example.com/file.tar.gz",
            expected_size=1024,
            etag='"xyz"',
            last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
            expected_sha256="abc123",
            segments=[SegmentInfo(start=0, current=512, end=1023)],
            created_at=100.0,
            updated_at=105.0,
        )
        raw = meta.to_json()
        loaded = DownloadMetadata.from_json(raw)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.url, meta.url)
        self.assertEqual(loaded.expected_size, meta.expected_size)
        self.assertEqual(loaded.etag, meta.etag)
        self.assertEqual(loaded.last_modified, meta.last_modified)
        self.assertEqual(loaded.expected_sha256, meta.expected_sha256)
        self.assertEqual(len(loaded.segments), 1)
        self.assertEqual(loaded.segments[0].start, 0)
        self.assertEqual(loaded.segments[0].current, 512)
        self.assertEqual(loaded.segments[0].end, 1023)

    def test_full_single_stream_download(self):
        engine = DownloadEngine()
        dest = self.work_dir / "testfile.bin"

        probe_resp = MagicMock()
        probe_resp.status = 200
        probe_resp.headers = {"Content-Length": "12"}
        probe_resp.__enter__.return_value = probe_resp

        data_resp = MagicMock()
        data_resp.status = 200
        data_resp.headers = {"Content-Length": "12"}
        data_resp.read.side_effect = [b"hello ", b"world!", b""]
        data_resp.__enter__.return_value = data_resp

        with patch("urllib.request.urlopen", side_effect=[probe_resp, data_resp]):
            out_path = engine.download("https://example.com/test.bin", dest)

        self.assertEqual(out_path, dest)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_bytes(), b"hello world!")
        part_path = dest.with_name("testfile.bin.part")
        self.assertFalse(part_path.exists())
        self.assertFalse(engine._meta_path(part_path).exists())

    def test_parallel_chunk_download(self):
        # 12 MB file (> 10MB threshold)
        total_size = 12 * 1024 * 1024
        engine = DownloadEngine(max_workers=2)
        dest = self.work_dir / "large.bin"

        # Probe response: returns 206 with Content-Range
        probe_resp = MagicMock()
        probe_resp.status = 206
        probe_resp.headers = {
            "Content-Range": f"bytes 0-0/{total_size}",
            "ETag": '"etag-large"',
            "Accept-Ranges": "bytes",
        }
        probe_resp.__enter__.return_value = probe_resp

        half = total_size // 2

        # Worker 1 response
        chunk1 = b"A" * 1024
        worker1_resp = MagicMock()
        worker1_resp.read.side_effect = [chunk1, b""]
        worker1_resp.__enter__.return_value = worker1_resp

        # Worker 2 response
        chunk2 = b"B" * 1024
        worker2_resp = MagicMock()
        worker2_resp.read.side_effect = [chunk2, b""]
        worker2_resp.__enter__.return_value = worker2_resp

        # Mock segment worker responses
        def fake_urlopen(req, **kwargs):
            if req.headers.get("Range") == "bytes=0-0":
                return probe_resp
            rng = req.headers.get("Range", "")
            if rng.startswith(f"bytes=0-{half - 1}"):
                return worker1_resp
            return worker2_resp

        with (
            patch.object(
                engine,
                "_probe_resource",
                return_value=(total_size, '"etag-large"', None, True),
            ),
            patch("urllib.request.urlopen", side_effect=[worker1_resp, worker2_resp]),
            patch.object(
                SegmentInfo,
                "is_complete",
                new_callable=lambda: property(lambda s: True),
            ),
        ):
            out_path = engine.download("https://example.com/large.bin", dest)

        self.assertEqual(out_path, dest)
        self.assertTrue(dest.is_file())

    def test_interruption_preserves_partial(self):
        engine = DownloadEngine()
        dest = self.work_dir / "interrupted.bin"
        part_path = dest.with_name("interrupted.bin.part")

        probe_resp = MagicMock()
        probe_resp.status = 200
        probe_resp.headers = {"Content-Length": "100"}
        probe_resp.__enter__.return_value = probe_resp

        data_resp = MagicMock()
        data_resp.status = 200
        data_resp.headers = {"Content-Length": "100"}
        data_resp.read.side_effect = [b"chunk1", KeyboardInterrupt()]
        data_resp.__enter__.return_value = data_resp

        with (
            patch("urllib.request.urlopen", side_effect=[probe_resp, data_resp]),
            self.assertRaises(SystemExit),
        ):
            engine.download("https://example.com/interrupted.bin", dest)

        self.assertTrue(part_path.is_file())
        self.assertEqual(part_path.read_bytes(), b"chunk1")
        self.assertTrue(engine._meta_path(part_path).is_file())

    def test_fetch_cached_file_flow(self):
        dest = self.work_dir / "cached.bin"
        dest.write_bytes(b"ship cached content")
        expected_sha = calc_sha256(dest)

        with patch("urllib.request.urlopen") as mock_url:
            p = fetch_cached_file(
                "https://example.com/cached.bin",
                dest,
                expected_sha256=expected_sha,
            )
            mock_url.assert_not_called()
            self.assertEqual(p, dest)

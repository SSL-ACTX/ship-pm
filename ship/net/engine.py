"""Robust, multi-segmented parallel resumable download engine with pipelined verification."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import signal
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from ship import __version__
from ship.ui import Progress, die, status, warn

DEFAULT_USER_AGENT = f"ship/{__version__}"
MIN_CHUNK_SIZE = 64 * 1024  # 64 KB
MAX_CHUNK_SIZE = 1024 * 1024  # 1 MB
PARALLEL_THRESHOLD_BYTES = (
    10 * 1024 * 1024
)  # 10 MB: files smaller than this use single stream


@dataclass
class SegmentInfo:
    start: int
    current: int
    end: int  # inclusive end byte offset

    @property
    def remaining(self) -> int:
        return max(0, self.end - self.current + 1)

    @property
    def is_complete(self) -> bool:
        return self.current > self.end


@dataclass
class DownloadMetadata:
    url: str
    expected_size: int | None
    etag: str | None
    last_modified: str | None
    expected_sha256: str | None
    segments: list[SegmentInfo] | None
    created_at: float
    updated_at: float

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> DownloadMetadata | None:
        try:
            data = json.loads(raw)
            segs_raw = data.get("segments")
            segments = (
                [
                    SegmentInfo(start=s["start"], current=s["current"], end=s["end"])
                    for s in segs_raw
                ]
                if segs_raw
                else None
            )
            return cls(
                url=data.get("url", ""),
                expected_size=data.get("expected_size"),
                etag=data.get("etag"),
                last_modified=data.get("last_modified"),
                expected_sha256=data.get("expected_sha256"),
                segments=segments,
                created_at=float(data.get("created_at", 0.0)),
                updated_at=float(data.get("updated_at", 0.0)),
            )
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            return None


class DownloadEngine:
    """Core download manager supporting parallel range streams and resumable transfers."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_workers: int = 4,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_workers = max_workers

    def _meta_path(self, part_path: Path) -> Path:
        return part_path.with_suffix(part_path.suffix + ".meta.json")

    def _read_meta(self, part_path: Path) -> DownloadMetadata | None:
        mpath = self._meta_path(part_path)
        if not mpath.is_file():
            return None
        try:
            return DownloadMetadata.from_json(mpath.read_text(encoding="utf-8"))
        except OSError:
            return None

    def _write_meta(self, part_path: Path, meta: DownloadMetadata) -> None:
        mpath = self._meta_path(part_path)
        try:
            fd, tmp = tempfile.mkstemp(prefix=".meta.", dir=part_path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(meta.to_json())
            os.replace(tmp, mpath)
        except OSError:
            pass

    def _remove_part_and_meta(self, part_path: Path) -> None:
        part_path.unlink(missing_ok=True)
        self._meta_path(part_path).unlink(missing_ok=True)

    def _probe_resource(
        self, url: str
    ) -> tuple[int | None, str | None, str | None, bool]:
        """Probe resource using Range: bytes=0-0 to check size and range capability."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Range": "bytes=0-0",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = getattr(resp, "status", 200)
                etag = resp.headers.get("ETag")
                last_modified = resp.headers.get("Last-Modified")
                content_range = resp.headers.get("Content-Range", "")
                total = None
                accepts_ranges = False

                if status_code == 206 and content_range:
                    accepts_ranges = True
                    parts = content_range.split("/")
                    if len(parts) == 2 and parts[1].isdigit():
                        total = int(parts[1])

                if total is None:
                    try:
                        total = int(resp.headers.get("Content-Length", ""))
                    except ValueError:
                        total = None

                return total, etag, last_modified, accepts_ranges
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            # Fallback to standard HEAD request if 206 probe is rejected
            try:
                head_req = urllib.request.Request(
                    url,
                    headers={"User-Agent": self.user_agent},
                    method="HEAD",
                )
                with urllib.request.urlopen(head_req, timeout=self.timeout) as resp:
                    cl = resp.headers.get("Content-Length")
                    total = int(cl) if cl and cl.isdigit() else None
                    etag = resp.headers.get("ETag")
                    lm = resp.headers.get("Last-Modified")
                    ar = resp.headers.get("Accept-Ranges", "").lower()
                    return total, etag, lm, (ar == "bytes")
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                return None, None, None, False

    def download(
        self,
        url: str,
        dest_path: Path,
        *,
        label: str | None = None,
        expected_sha256: str = "",
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_name(f"{dest_path.name}.part")
        display_name = label or Path(urllib.parse.urlsplit(url).path).name or url

        existing_meta = self._read_meta(part_path) if part_path.is_file() else None
        if existing_meta and existing_meta.url != url:
            self._remove_part_and_meta(part_path)
            existing_meta = None

        total_size, etag, last_mod, accepts_ranges = self._probe_resource(url)

        # Decide whether to use multi-connection parallel segment workers
        use_parallel = (
            accepts_ranges
            and total_size is not None
            and total_size >= PARALLEL_THRESHOLD_BYTES
            and self.max_workers > 1
        )

        if use_parallel:
            return self._download_parallel(
                url=url,
                dest_path=dest_path,
                part_path=part_path,
                display_name=display_name,
                total_size=total_size,  # pyright: ignore
                etag=etag,
                last_mod=last_mod,
                expected_sha256=expected_sha256,
                existing_meta=existing_meta,
                on_progress=on_progress,
            )
        else:
            return self._download_single_stream(
                url=url,
                dest_path=dest_path,
                part_path=part_path,
                display_name=display_name,
                total_size=total_size,
                etag=etag,
                last_mod=last_mod,
                expected_sha256=expected_sha256,
                existing_meta=existing_meta,
                on_progress=on_progress,
            )

    def _download_parallel(
        self,
        *,
        url: str,
        dest_path: Path,
        part_path: Path,
        display_name: str,
        total_size: int,
        etag: str | None,
        last_mod: str | None,
        expected_sha256: str,
        existing_meta: DownloadMetadata | None,
        on_progress: Callable[[int, int | None], None] | None,
    ) -> Path:
        # Open file without full preallocation (sparse writes via pwrite grow file naturally)
        fd = os.open(part_path, os.O_RDWR | os.O_CREAT, 0o644)

        num_workers = min(self.max_workers, 8)
        segments: list[SegmentInfo] = []

        # Validate if existing segments can be resumed
        can_resume_segs = False
        if (
            existing_meta
            and existing_meta.segments
            and existing_meta.expected_size == total_size
            and (existing_meta.etag == etag or existing_meta.last_modified == last_mod)
        ):
            segments = existing_meta.segments
            can_resume_segs = True

        if not can_resume_segs:
            part_size = total_size // num_workers
            segments = []
            for i in range(num_workers):
                seg_start = i * part_size
                seg_end = (
                    total_size - 1 if i == num_workers - 1 else (i + 1) * part_size - 1
                )
                segments.append(
                    SegmentInfo(start=seg_start, current=seg_start, end=seg_end)
                )

        action_name = "Resuming" if can_resume_segs else "Downloading"
        progress = Progress(action_name, display_name)
        progress.set_total(total_size)

        now = time.time()
        meta = DownloadMetadata(
            url=url,
            expected_size=total_size,
            etag=etag,
            last_modified=last_mod,
            expected_sha256=expected_sha256 or None,
            segments=segments,
            created_at=existing_meta.created_at if existing_meta else now,
            updated_at=now,
        )
        self._write_meta(part_path, meta)

        lock = threading.Lock()
        downloaded_bytes = sum(s.current - s.start for s in segments)
        progress.update(downloaded_bytes)

        stop_event = threading.Event()
        meta_dirty = False
        last_meta_save = time.monotonic()
        active_responses: set[object] = set()

        def _worker_fetch(seg_idx: int) -> None:
            nonlocal downloaded_bytes, meta_dirty, last_meta_save
            seg = segments[seg_idx]
            if seg.is_complete:
                return

            req_headers = {
                "User-Agent": self.user_agent,
                "Range": f"bytes={seg.current}-{seg.end}",
                "Accept-Encoding": "identity",
            }
            if etag:
                req_headers["If-Range"] = etag
            elif last_mod:
                req_headers["If-Range"] = last_mod

            req = urllib.request.Request(url, headers=req_headers)
            try:
                resp = urllib.request.urlopen(req, timeout=self.timeout)
            except (urllib.error.URLError, TimeoutError, OSError):
                if stop_event.is_set():
                    return
                raise

            with lock:
                active_responses.add(resp)

            try:
                chunk_size = 128 * 1024
                while not stop_event.is_set():
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    offset = seg.current
                    os.pwrite(fd, chunk, offset)
                    chunk_len = len(chunk)
                    with lock:
                        seg.current += chunk_len
                        downloaded_bytes += chunk_len
                        progress.update(downloaded_bytes)
                        if on_progress:
                            on_progress(downloaded_bytes, total_size)
                        meta_dirty = True
                        if time.monotonic() - last_meta_save > 4.0:
                            meta.updated_at = time.time()
                            self._write_meta(part_path, meta)
                            last_meta_save = time.monotonic()
                            meta_dirty = False
            except (OSError, TimeoutError):
                if not stop_event.is_set():
                    raise
            finally:
                with lock:
                    active_responses.discard(resp)
                try:
                    resp.close()
                except (OSError, ValueError):
                    pass

        old_sigint = None
        old_sigterm = None

        def _abort_all():
            stop_event.set()
            with lock:
                for r in list(active_responses):
                    try:
                        r.close()
                    except (OSError, ValueError):
                        pass
                active_responses.clear()

        def _handle_signal(signum, frame):
            _abort_all()
            progress.finish(success=False)
            raise KeyboardInterrupt

        try:
            if hasattr(signal, "SIGINT"):
                old_sigint = signal.signal(signal.SIGINT, _handle_signal)
            if hasattr(signal, "SIGTERM"):
                old_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, OSError, AttributeError):
            pass

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=num_workers)
        try:
            futures = [executor.submit(_worker_fetch, i) for i in range(len(segments))]
            for fut in concurrent.futures.as_completed(futures):
                fut.result()

            os.fsync(fd)
            os.close(fd)
            fd = -1

            # Validate full completion
            if not all(s.is_complete for s in segments):
                raise OSError("One or more parallel segments did not complete")

            # Forward inline SHA-256 validation if expected checksum supplied
            if expected_sha256:
                status("Verifying", f"SHA-256 checksum ({expected_sha256[:12]}...)...")
                actual_sha = self._calc_sha256(part_path)
                if actual_sha.lower() != expected_sha256.lower():
                    self._remove_part_and_meta(part_path)
                    die(
                        f"Checksum mismatch for {display_name}!\n  Expected: {expected_sha256}\n  Got:      {actual_sha}"
                    )

            # Move part to final destination and remove metadata
            os.replace(part_path, dest_path)
            self._meta_path(part_path).unlink(missing_ok=True)

            progress.update(total_size, total_size)
            progress.finish(success=True)
            return dest_path

        except KeyboardInterrupt:
            _abort_all()
            executor.shutdown(wait=False, cancel_futures=True)
            if fd >= 0:
                try:
                    os.fsync(fd)
                    os.close(fd)
                except OSError:
                    pass
            meta.updated_at = time.time()
            self._write_meta(part_path, meta)
            progress.finish(success=False)
            warn(f"Download paused for {display_name}. Run again to resume.")
            sys.exit(130)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            _abort_all()
            executor.shutdown(wait=False, cancel_futures=True)
            if fd >= 0:
                try:
                    os.fsync(fd)
                    os.close(fd)
                except OSError:
                    pass
            meta.updated_at = time.time()
            self._write_meta(part_path, meta)
            progress.finish(success=False)
            warn(
                f"Download interrupted ({e}); partial chunks preserved for resumption."
            )
            die(f"Download failed from {url}: {e}")
            sys.exit(1)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                if old_sigint and hasattr(signal, "SIGINT"):
                    signal.signal(signal.SIGINT, old_sigint)
                if old_sigterm and hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, old_sigterm)
            except (ValueError, OSError, AttributeError):
                pass

    def _download_single_stream(
        self,
        *,
        url: str,
        dest_path: Path,
        part_path: Path,
        display_name: str,
        total_size: int | None,
        etag: str | None,
        last_mod: str | None,
        expected_sha256: str,
        existing_meta: DownloadMetadata | None,
        on_progress: Callable[[int, int | None], None] | None,
    ) -> Path:
        existing_part_size = 0
        if part_path.is_file():
            try:
                existing_part_size = part_path.stat().st_size
            except OSError:
                existing_part_size = 0

        can_resume = (
            existing_part_size > 0
            and existing_meta is not None
            and (existing_meta.etag == etag or existing_meta.last_modified == last_mod)
        )

        req_headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
        }

        if can_resume:
            req_headers["Range"] = f"bytes={existing_part_size}-"
            if etag:
                req_headers["If-Range"] = etag
            elif last_mod:
                req_headers["If-Range"] = last_mod

        req = urllib.request.Request(url, headers=req_headers)
        action_name = "Resuming" if can_resume else "Downloading"
        progress = Progress(action_name, display_name)

        # Inline forward streaming hasher if starting from scratch
        inline_hasher = (
            hashlib.sha256() if (not can_resume and expected_sha256) else None
        )

        old_sigint = None
        old_sigterm = None

        active_resp = None

        def _handle_signal(signum, frame):
            if active_resp:
                try:
                    active_resp.close()
                except (OSError, ValueError):
                    pass
            progress.finish(success=False)
            raise KeyboardInterrupt

        try:
            if hasattr(signal, "SIGINT"):
                old_sigint = signal.signal(signal.SIGINT, _handle_signal)
            if hasattr(signal, "SIGTERM"):
                old_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, OSError, AttributeError):
            pass

        try:
            try:
                resp = urllib.request.urlopen(req, timeout=self.timeout)
                active_resp = resp
            except urllib.error.HTTPError as he:
                if he.code == 416 and existing_part_size > 0:
                    self._remove_part_and_meta(part_path)
                    req_headers.pop("Range", None)
                    req_headers.pop("If-Range", None)
                    req = urllib.request.Request(url, headers=req_headers)
                    resp = urllib.request.urlopen(req, timeout=self.timeout)
                    can_resume = False
                    existing_part_size = 0
                    inline_hasher = hashlib.sha256() if expected_sha256 else None
                else:
                    raise

            with resp:
                status_code = getattr(resp, "status", 200)
                resp_headers = resp.headers

                resp_etag = resp_headers.get("ETag") or etag
                resp_last_mod = resp_headers.get("Last-Modified") or last_mod
                content_length_str = resp_headers.get("Content-Length", "")
                try:
                    content_length = int(content_length_str)
                except ValueError:
                    content_length = None

                is_resuming = status_code == 206 and can_resume

                if is_resuming:
                    total_expected = (
                        existing_part_size + content_length
                        if content_length is not None
                        else (
                            existing_meta.expected_size if existing_meta else total_size
                        )
                    )
                    file_mode = "ab"
                    current_bytes = existing_part_size
                else:
                    total_expected = content_length or total_size
                    file_mode = "wb"
                    current_bytes = 0
                    if not is_resuming and existing_part_size > 0:
                        self._remove_part_and_meta(part_path)

                now = time.time()
                meta = DownloadMetadata(
                    url=url,
                    expected_size=total_expected,
                    etag=resp_etag,
                    last_modified=resp_last_mod,
                    expected_sha256=expected_sha256 or None,
                    segments=None,
                    created_at=existing_meta.created_at if existing_meta else now,
                    updated_at=now,
                )
                self._write_meta(part_path, meta)

                progress.set_total(total_expected)
                progress.update(current_bytes)

                chunk_size = MIN_CHUNK_SIZE
                last_meta_save = time.monotonic()

                with open(part_path, file_mode) as out_f:
                    while True:
                        t0 = time.monotonic()
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        dt = time.monotonic() - t0

                        out_f.write(chunk)
                        if inline_hasher is not None:
                            inline_hasher.update(chunk)

                        current_bytes += len(chunk)
                        progress.update(current_bytes)
                        if on_progress:
                            on_progress(current_bytes, total_expected)

                        if dt > 0 and len(chunk) == chunk_size:
                            speed = len(chunk) / dt
                            if speed > 2 * chunk_size and chunk_size < MAX_CHUNK_SIZE:
                                chunk_size = min(chunk_size * 2, MAX_CHUNK_SIZE)
                            elif speed < chunk_size / 2 and chunk_size > MIN_CHUNK_SIZE:
                                chunk_size = max(chunk_size // 2, MIN_CHUNK_SIZE)

                        if time.monotonic() - last_meta_save > 5.0:
                            meta.updated_at = time.time()
                            self._write_meta(part_path, meta)
                            last_meta_save = time.monotonic()

                    out_f.flush()
                    os.fsync(out_f.fileno())

            if total_expected is not None and current_bytes != total_expected:
                raise OSError(
                    f"Incomplete download: received {current_bytes} bytes of {total_expected}"
                )

            # Verification: use forward inline hash if available, or compute once
            if expected_sha256:
                status("Verifying", f"SHA-256 checksum ({expected_sha256[:12]}...)...")
                actual_sha = (
                    inline_hasher.hexdigest()
                    if inline_hasher is not None
                    else self._calc_sha256(part_path)
                )
                if actual_sha.lower() != expected_sha256.lower():
                    self._remove_part_and_meta(part_path)
                    die(
                        f"Checksum mismatch for {display_name}!\n  Expected: {expected_sha256}\n  Got:      {actual_sha}"
                    )

            os.replace(part_path, dest_path)
            self._meta_path(part_path).unlink(missing_ok=True)

            progress.update(current_bytes, total_expected)
            progress.finish(success=True)
            return dest_path

        except KeyboardInterrupt:
            progress.finish(success=False)
            warn(f"Download paused for {display_name}. Run again to resume.")
            sys.exit(130)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            progress.finish(success=False)
            warn(
                f"Download interrupted ({e}); partial download preserved for resumption."
            )
            die(f"Download failed from {url}: {e}")
            sys.exit(1)
        finally:
            try:
                if old_sigint and hasattr(signal, "SIGINT"):
                    signal.signal(signal.SIGINT, old_sigint)
                if old_sigterm and hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, old_sigterm)
            except (ValueError, OSError, AttributeError):
                pass

    def _calc_sha256(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


_DEFAULT_ENGINE = DownloadEngine()


def get_default_engine() -> DownloadEngine:
    return _DEFAULT_ENGINE

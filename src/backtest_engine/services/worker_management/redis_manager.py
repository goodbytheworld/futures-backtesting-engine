"""
Managed local Redis lifecycle for terminal UI scenario jobs.
"""

from __future__ import annotations

import socket
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Literal, Optional

from src.backtest_engine.services.paths import get_results_dir

from .common import read_log_tail, utc_now_iso


RedisLifecycleState = Literal["stopped", "starting", "live", "error"]


@dataclass(frozen=True)
class ManagedRedisSnapshot:
    """
    Captures the current state of the app-owned local Redis process.

    Methodology:
        Liveness is determined with a TCP connection check instead of a simple
        grace-period timer so the UI reflects real reachability.
    """

    state: RedisLifecycleState
    is_live: bool
    started_by_app: bool
    pid: Optional[int]
    started_at: str
    exit_code: Optional[int]
    last_error: str
    log_path: str
    host: str
    port: int

    def to_public_dict(self) -> dict[str, object]:
        """Returns a JSON-safe representation for UI rendering."""
        return asdict(self)


class LocalRedisManager:
    """
    Manages one local ``redis-server`` subprocess for the dashboard session.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        results_dir: Optional[str],
        project_root: Path,
    ) -> None:
        self._host = host
        self._port = port
        self.project_root = project_root
        self.results_root = (
            Path(results_dir) if results_dir is not None else get_results_dir()
        )
        self.log_path = self.results_root / "jobs" / "managed-redis.log"
        self._process: Optional[subprocess.Popen[str]] = None
        self._log_handle: Optional[IO[str]] = None
        self._started_at: str = ""
        self._exit_code: Optional[int] = None
        self._last_error: str = ""
        self._state_hint: RedisLifecycleState = "stopped"
        self._lock = threading.Lock()

    def _build_command(self) -> list[str]:
        """Builds the ``redis-server`` command for the configured host and port."""
        return ["redis-server", "--port", str(self._port), "--bind", self._host]

    def _ping(self) -> bool:
        """Checks whether Redis is accepting TCP connections."""
        try:
            with socket.create_connection((self._host, self._port), timeout=0.5):
                return True
        except OSError:
            return False

    def _write_log_banner(self, action: str) -> None:
        """Appends a small lifecycle banner to the Redis log."""
        if self._log_handle is None:
            return
        self._log_handle.write(f"\n[{utc_now_iso()}] {action}\n")
        self._log_handle.flush()

    def _close_log_handle_locked(self) -> None:
        """Closes the log file handle when one is open."""
        if self._log_handle is None:
            return
        try:
            self._log_handle.flush()
        except Exception:
            pass
        try:
            self._log_handle.close()
        except Exception:
            pass
        self._log_handle = None

    def _sync_process_state_locked(self) -> None:
        """Synchronizes stored state from the current subprocess handle."""
        if self._process is None:
            return
        exit_code = self._process.poll()
        if exit_code is None:
            return
        self._exit_code = int(exit_code)
        if exit_code == 0:
            self._state_hint = "stopped"
        else:
            self._state_hint = "error"
            if not self._last_error:
                tail = read_log_tail(self.log_path)
                tail_message = f" Log tail: {tail}" if tail else ""
                self._last_error = (
                    f"redis-server exited with code {exit_code}.{tail_message}"
                )
        self._process = None
        self._close_log_handle_locked()

    def _snapshot_locked(self) -> ManagedRedisSnapshot:
        """
        Builds the current Redis snapshot while the state lock is held.

        Methodology:
            Ping is checked even when the app does not own the process so a
            service-installed Redis instance still appears as live.
        """
        self._sync_process_state_locked()
        state = self._state_hint
        is_live = False
        pid: Optional[int] = None
        if self._process is not None and self._process.poll() is None:
            pid = int(self._process.pid) if self._process.pid is not None else None
            if self._ping():
                state = "live"
                is_live = True
            else:
                state = "starting"
        elif state != "error":
            if self._ping():
                state = "live"
                is_live = True
            else:
                state = "stopped"
        return ManagedRedisSnapshot(
            state=state,
            is_live=is_live,
            started_by_app=bool(self._started_at),
            pid=pid,
            started_at=self._started_at,
            exit_code=self._exit_code,
            last_error=self._last_error,
            log_path=str(self.log_path.resolve()),
            host=self._host,
            port=self._port,
        )

    def snapshot(self) -> ManagedRedisSnapshot:
        """Returns the current Redis snapshot."""
        with self._lock:
            return self._snapshot_locked()

    def start_redis(self) -> ManagedRedisSnapshot:
        """
        Starts ``redis-server`` unless it is already live or starting.

        Returns:
            Fresh Redis snapshot after the start attempt.
        """
        with self._lock:
            current = self._snapshot_locked()
            if current.state in {"starting", "live"}:
                return current
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._last_error = ""
            self._exit_code = None
            self._started_at = utc_now_iso()
            self._state_hint = "starting"
            try:
                self._log_handle = self.log_path.open("a", encoding="utf-8")
                self._write_log_banner("Starting managed redis-server")
                self._process = subprocess.Popen(
                    self._build_command(),
                    cwd=str(self.project_root),
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except FileNotFoundError:
                self._process = None
                self._state_hint = "error"
                self._last_error = (
                    "redis-server not found in PATH. "
                    "Install Redis for Windows: run 'winget install Redis.Redis' in a terminal, "
                    "then restart the dashboard."
                )
                self._close_log_handle_locked()
            except Exception as exc:
                self._process = None
                self._state_hint = "error"
                self._last_error = str(exc)
                self._close_log_handle_locked()
            return self._snapshot_locked()

    def stop_redis(self) -> ManagedRedisSnapshot:
        """
        Stops the managed Redis subprocess when owned by the app.

        Returns:
            Fresh Redis snapshot after the stop attempt.
        """
        with self._lock:
            self._sync_process_state_locked()
            if self._process is None or self._process.poll() is not None:
                if self._state_hint != "error":
                    self._state_hint = "stopped"
                return self._snapshot_locked()
            try:
                self._write_log_banner("Stopping managed redis-server")
                self._process.terminate()
                self._process.wait(timeout=5.0)
            except Exception:
                try:
                    self._process.kill()
                    self._process.wait(timeout=5.0)
                except Exception as exc:
                    self._state_hint = "error"
                    self._last_error = str(exc)
            finally:
                if self._process is not None:
                    self._exit_code = self._process.returncode
                self._process = None
                if self._state_hint != "error":
                    self._state_hint = "stopped"
                    self._last_error = ""
                self._close_log_handle_locked()
            return self._snapshot_locked()

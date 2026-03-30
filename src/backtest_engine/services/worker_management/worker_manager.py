"""
Managed local worker lifecycle for terminal UI scenario jobs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, Optional

from src.backtest_engine.services.paths import get_results_dir

from .common import read_log_tail, utc_now_iso

if TYPE_CHECKING:
    from src.backtest_engine.services.scenario_job_service import TerminalQueueConfig


WorkerLifecycleState = Literal["stopped", "starting", "running", "crashed"]


@dataclass(frozen=True)
class ManagedWorkerSnapshot:
    """
    Captures the current state of the app-owned local worker process.

    Methodology:
        The terminal UI consumes a JSON-safe lifecycle snapshot rather than raw
        subprocess objects, allowing routes and tests to inspect the worker
        state without sharing process handles.
    """

    state: WorkerLifecycleState
    is_running: bool
    started_by_app: bool
    pid: Optional[int]
    started_at: str
    exit_code: Optional[int]
    last_error: str
    log_path: str
    command: str

    def to_public_dict(self) -> dict[str, object]:
        """Returns a JSON-safe representation for UI rendering."""
        return asdict(self)


class LocalWorkerManager:
    """
    Manages one local RQ worker subprocess for the dashboard session.

    Methodology:
        The manager owns only app-started worker lifecycle. It does not change
        queue semantics or Redis behavior; it provides a stable way for the
        Stress Testing UI to start, stop, and inspect a compatible worker.
    """

    def __init__(
        self,
        *,
        config: "TerminalQueueConfig",
        results_dir: Optional[str],
        project_root: Path,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.results_root = (
            Path(results_dir) if results_dir is not None else get_results_dir()
        )
        self.log_path = self.results_root / "jobs" / "managed-worker.log"
        self._process: Optional[subprocess.Popen[str]] = None
        self._log_handle: Optional[IO[str]] = None
        self._started_at: str = ""
        self._exit_code: Optional[int] = None
        self._last_error: str = ""
        self._state_hint: WorkerLifecycleState = "stopped"
        self._lock = threading.Lock()

    def _resolve_rq_executable(self) -> str:
        """
        Resolves the RQ console-script path for the active environment.

        Methodology:
            ``rq`` does not reliably support ``python -m rq`` in every setup, so
            the manager resolves the installed script first and only falls back
            to common virtualenv locations adjacent to ``sys.executable``.
        """
        found = shutil.which("rq")
        if found:
            return found
        scripts_dir = Path(sys.executable).parent
        candidates = [
            scripts_dir / "rq.exe",
            scripts_dir / "rq",
            scripts_dir / "Scripts" / "rq.exe",
            scripts_dir / "Scripts" / "rq",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "rq"

    def _build_command(self) -> list[str]:
        """
        Builds the worker command for the configured queue.

        Methodology:
            Windows cannot rely on ``os.fork()``, so the dashboard uses the
            custom SimpleWorker implementation that executes jobs in-process.
        """
        command = [self._resolve_rq_executable(), "worker"]
        if self.config.redis_url:
            command.extend(["--url", self.config.redis_url])
        if sys.platform == "win32":
            command.extend(
                [
                    "--worker-class",
                    "src.backtest_engine.runtime.terminal_ui.windows_worker.WindowsSimpleWorker",
                ]
            )
        command.append(self.config.queue_name)
        return command

    def _command_display(self) -> str:
        """Formats the worker command for diagnostics and UI display."""
        return subprocess.list2cmdline(self._build_command())

    def _write_log_banner(self, action: str) -> None:
        """Appends a small lifecycle banner to the worker log."""
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

    def _snapshot_locked(self) -> ManagedWorkerSnapshot:
        """Builds a worker snapshot while the state lock is held."""
        self._sync_process_state_locked()
        state = self._state_hint
        is_running = False
        pid: Optional[int] = None
        if self._process is not None and self._process.poll() is None:
            pid = int(self._process.pid) if self._process.pid is not None else None
            is_running = True
            if self._started_at:
                started_dt = datetime.fromisoformat(self._started_at)
                elapsed_seconds = (
                    datetime.now(timezone.utc) - started_dt
                ).total_seconds()
                if elapsed_seconds >= float(self.config.worker_start_grace_seconds):
                    state = "running"
                else:
                    state = "starting"
            else:
                state = "starting"
        elif state != "crashed":
            state = "stopped"
        return ManagedWorkerSnapshot(
            state=state,
            is_running=is_running,
            started_by_app=bool(self._started_at),
            pid=pid,
            started_at=self._started_at,
            exit_code=self._exit_code,
            last_error=self._last_error,
            log_path=str(self.log_path.resolve()),
            command=self._command_display(),
        )

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
            if not self._last_error:
                self._last_error = ""
        else:
            self._state_hint = "crashed"
            if not self._last_error:
                tail = read_log_tail(self.log_path)
                tail_message = f" Log tail: {tail}" if tail else ""
                self._last_error = (
                    f"Worker exited with code {exit_code}.{tail_message}"
                )
        self._process = None
        self._close_log_handle_locked()

    def snapshot(self) -> ManagedWorkerSnapshot:
        """Returns the current worker snapshot."""
        with self._lock:
            return self._snapshot_locked()

    def start_worker(self) -> ManagedWorkerSnapshot:
        """
        Starts the managed worker unless one is already active.

        Returns:
            Fresh worker snapshot after the start attempt.
        """
        with self._lock:
            current = self._snapshot_locked()
            if current.state in {"starting", "running"}:
                return current
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._last_error = ""
            self._exit_code = None
            self._started_at = utc_now_iso()
            self._state_hint = "starting"
            try:
                self._log_handle = self.log_path.open("a", encoding="utf-8")
                self._write_log_banner("Starting managed worker")
                env = None
                if sys.platform == "win32":
                    env = dict(os.environ)
                    project_root_str = str(self.project_root)
                    env["PYTHONPATH"] = (
                        project_root_str
                        if "PYTHONPATH" not in env
                        else f"{project_root_str}{os.pathsep}{env['PYTHONPATH']}"
                    )
                self._process = subprocess.Popen(
                    self._build_command(),
                    cwd=str(self.project_root),
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                )
            except Exception as exc:
                self._process = None
                self._state_hint = "crashed"
                self._last_error = str(exc)
                self._close_log_handle_locked()
            return self._snapshot_locked()

    def stop_worker(self) -> ManagedWorkerSnapshot:
        """
        Stops the managed worker if it is currently active.

        Returns:
            Fresh worker snapshot after the stop attempt.
        """
        with self._lock:
            self._sync_process_state_locked()
            if self._process is None or self._process.poll() is not None:
                if self._state_hint != "crashed":
                    self._state_hint = "stopped"
                return self._snapshot_locked()
            try:
                self._write_log_banner("Stopping managed worker")
                self._process.terminate()
                self._process.wait(
                    timeout=float(self.config.worker_stop_timeout_seconds)
                )
            except Exception:
                try:
                    self._process.kill()
                    self._process.wait(
                        timeout=float(self.config.worker_stop_timeout_seconds)
                    )
                except Exception as exc:
                    self._state_hint = "crashed"
                    self._last_error = str(exc)
            finally:
                if self._process is not None:
                    self._exit_code = self._process.returncode
                self._process = None
                if self._state_hint != "crashed":
                    self._state_hint = "stopped"
                    self._last_error = ""
                self._close_log_handle_locked()
            return self._snapshot_locked()

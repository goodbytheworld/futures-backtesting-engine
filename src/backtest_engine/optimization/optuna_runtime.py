"""
Shared Optuna runtime helpers for optimization workflows.
"""

from __future__ import annotations

import os
import sys
from importlib import import_module
from typing import Any, cast


try:
    OPTUNA = import_module("optuna")
except ImportError:
    OPTUNA = cast(Any, None)

Trial = Any


def require_optuna() -> Any:
    """Returns the imported Optuna module or raises a clear install error."""
    if OPTUNA is None:
        raise ImportError(
            "Optuna is required for optimization. Install it with: pip install optuna"
        )
    return OPTUNA


def set_optuna_warning_verbosity() -> None:
    """Silences Optuna trial logs when the dependency is installed."""
    if OPTUNA is not None:
        OPTUNA.logging.set_verbosity(OPTUNA.logging.WARNING)


def restore_optuna_info_verbosity() -> None:
    """Restores Optuna logging to INFO when the dependency is installed."""
    if OPTUNA is not None:
        OPTUNA.logging.set_verbosity(OPTUNA.logging.INFO)


class HiddenPrints:
    """
    Suppresses stdout and stderr during optimization trial execution.
    """

    def __enter__(self) -> None:
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._null_stream = open(os.devnull, "w")
        sys.stdout = self._null_stream
        sys.stderr = self._null_stream

    def __exit__(self, *_: object) -> None:
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        self._null_stream.close()

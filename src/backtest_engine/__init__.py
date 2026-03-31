"""
Backtest engine package.

Canonical packages:
- `single_asset/` for the single-instrument event loop and local portfolio book
- `execution/` for shared order, fill, and execution-kernel code
- `config/` for runtime settings models
- `portfolio_layer/` for the multi-strategy shared-capital engine
- `runtime/` for the terminal UI runtime surface
"""

from .config import BacktestSettings, ScenarioEngineSettings, TerminalUISettings
from .single_asset import BacktestEngine

__all__ = [
    "BacktestEngine",
    "BacktestSettings",
    "TerminalUISettings",
    "ScenarioEngineSettings",
]

"""
Typed contracts for lightweight batch orchestration.

Methodology:
    Batch workflows fan out many independent single-strategy runs.  Small
    dataclasses keep the CLI, worker, plotting, and export layers aligned
    without passing anonymous dictionaries through the process boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BatchScenario:
    """
    One independent single-strategy run target.

    Args:
        strategy_id: Canonical strategy registry ID.
        symbol: Futures symbol to load from cache.
        timeframe: Timeframe suffix ('1m', '5m', '30m', '1h').
    """

    strategy_id: str
    symbol: str
    timeframe: str

    @property
    def scenario_id(self) -> str:
        """Returns a filesystem-safe scenario identifier."""
        return f"{self.strategy_id}__{self.symbol}__{self.timeframe}"

    @property
    def legend_label(self) -> str:
        """Returns the compact display label used in charts and tables."""
        return f"{self.strategy_id} | {self.symbol} | {self.timeframe}"


@dataclass
class SingleBatchResult:
    """
    Lightweight result payload for the simple batch backtest plot.

    Methodology:
        Workers return only the normalized equity path and the three requested
        KPIs so the parent process can render one Matplotlib popup without
        serializing full engine objects.
    """

    scenario: BatchScenario
    status: str
    timestamps: List[Any] = field(default_factory=list)
    log_equity: List[float] = field(default_factory=list)
    pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    error: Optional[str] = None


@dataclass
class WfoBatchResult:
    """
    Lightweight summary payload for one walk-forward batch scenario.

    Methodology:
        Batch UX needs a compact verdict-focused view in the terminal and a
        separate exportable record for candidate parameters.  The dataclass
        mirrors the stable surface of ``WFVReport`` used by the new service.
    """

    scenario: BatchScenario
    status: str
    verdict: str = "FAIL"
    n_folds: int = 0
    median_oos_score: float = 0.0
    median_degradation: float = 0.0
    avg_dsr: float = 0.0
    total_wfo_time_sec: float = 0.0
    avg_fold_time_sec: float = 0.0
    avg_trial_time_sec: float = 0.0
    candidate_params: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    text_report: str = ""
    error: Optional[str] = None

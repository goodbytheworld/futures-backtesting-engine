"""
Walk-forward optimization orchestration for event-driven strategies.
"""

from __future__ import annotations

import time
from typing import Optional, Type

from src.data.data_lake import DataLake

from ..settings import BacktestSettings
from .fold_generator import PurgedFoldGenerator
from .optimizer import OptunaOptimizer
from .optuna_runtime import require_optuna, set_optuna_warning_verbosity
from .wfv_report import FoldResult, WFVReport, format_human_report


class WalkForwardOptimizer:
    """
    Orchestrates research-grade walk-forward validation.

    Methodology:
        Full datasets are loaded once, split into purged folds, optimized on
        in-sample windows, then evaluated on out-of-sample windows using the
        same event-driven engine semantics as normal strategy runs.
    """

    def __init__(self, settings: Optional[BacktestSettings] = None) -> None:
        """Initializes the walk-forward optimizer."""
        if settings is None:
            raise ValueError("BacktestSettings must be provided to WalkForwardOptimizer.")
        self.settings = settings
        self.base_optimizer = OptunaOptimizer(settings=self.settings)
        self.data_lake = DataLake(self.settings)

    def run(
        self,
        strategy_class: Type,
        n_folds: Optional[int] = None,
        test_size_pct: Optional[float] = None,
        n_trials: Optional[int] = None,
        purge_bars: int = 0,
        embargo_bars: int = 0,
        anchored: bool = False,
        verbose: bool = True,
        print_report: bool = True,
        show_progress_bar: bool = True,
    ) -> WFVReport:
        """Runs walk-forward validation for a strategy class."""
        require_optuna()
        n_folds = n_folds or self.settings.wfo_n_folds
        test_size_pct = test_size_pct or self.settings.wfo_test_size_pct
        n_trials = n_trials or self.settings.wfo_n_trials

        symbol = self.settings.default_symbol
        timeframe = self.settings.low_interval

        if verbose:
            print(f"\n[WFV] Loading {symbol} @ {timeframe} for fold generation...")
        data = self.data_lake.load(symbol, timeframe=timeframe)
        if data.empty:
            if verbose:
                print("[WFV] No data found. Aborting.")
            return WFVReport(symbol, strategy_class.__name__, 0, [])

        if verbose:
            print(
                f"[WFV] Data range: {data.index[0].date()} -> {data.index[-1].date()} "
                f"| {len(data):,} bars"
            )

        splitter = PurgedFoldGenerator(
            n_folds=n_folds,
            test_size=test_size_pct,
            purge_bars=purge_bars,
            embargo_bars=embargo_bars,
            anchored=anchored,
        )
        folds = list(splitter.split(data))
        fold_results: list[FoldResult] = []
        total_trials = 0
        wfo_start_time = time.time()

        set_optuna_warning_verbosity()
        if verbose:
            print(f"\n[WFV] Starting {n_folds}-Fold Walk-Forward on {symbol}...")

        for fold_index, (train_idx, test_idx) in enumerate(folds, start=1):
            train_start = data.index[train_idx[0]]
            train_end = data.index[train_idx[-1]]
            test_start = data.index[test_idx[0]]
            test_end = data.index[test_idx[-1]]
            train_slice = data.iloc[train_idx]
            test_slice = data.iloc[test_idx]

            if verbose:
                print(
                    f"\n  Fold {fold_index}/{len(folds)}: "
                    f"IS {train_start.date()} -> {train_end.date()} | "
                    f"OOS {test_start.date()} -> {test_end.date()}"
                )

            fold_start_time = time.time()
            opt_result = self.base_optimizer.optimize_on_slice(
                strategy_class=strategy_class,
                start_date=train_start,
                end_date=train_end,
                data=train_slice,
                n_trials=n_trials,
                fold_id=fold_index - 1,
                show_progress_bar=show_progress_bar,
            )
            n_trials_actual = opt_result.get("n_trials", n_trials)
            total_trials += n_trials_actual
            trial_std = opt_result.get("trial_std", 0.0)
            oos_min_trades = self.base_optimizer.scale_min_trades_for_window(
                target_bars=len(test_slice),
                reference_bars=len(train_slice),
            )

            if opt_result["best_score"] <= 0.0 or not opt_result["best_params"]:
                failure_reason = opt_result.get(
                    "failure_reason",
                    "IS optimization failed quality gates.",
                )
                eval_result = {
                    "score": -1.0,
                    "stats": {},
                    "rejection_reason": failure_reason,
                }
            else:
                eval_result = self.base_optimizer.evaluate_on_slice(
                    strategy_class=strategy_class,
                    params=opt_result["best_params"],
                    start_date=test_start,
                    end_date=test_end,
                    data=test_slice,
                    min_trades_override=oos_min_trades,
                )
            fold_end_time = time.time()

            fold_results.append(
                FoldResult(
                    fold_id=fold_index,
                    train_start=str(train_start.date()),
                    train_end=str(train_end.date()),
                    test_start=str(test_start.date()),
                    test_end=str(test_end.date()),
                    best_params=opt_result["best_params"],
                    is_score=opt_result["best_score"],
                    oos_score=eval_result["score"],
                    n_trials=n_trials_actual,
                    trial_std=trial_std,
                    is_stats=opt_result.get("best_stats", {}),
                    oos_stats=eval_result["stats"],
                    oos_rejection_reason=eval_result.get("rejection_reason"),
                    oos_min_trades_required=oos_min_trades,
                )
            )

            if verbose:
                print(
                    f"  Fold {fold_index}: IS {opt_result['best_score']:.2f} -> "
                    f"OOS {eval_result['score']:.2f} "
                    f"({fold_end_time - fold_start_time:.1f}s)"
                )

        total_time = time.time() - wfo_start_time
        report = WFVReport(
            symbol=symbol,
            strategy_name=strategy_class.__name__,
            n_folds=len(folds),
            fold_results=fold_results,
            pass_min_profitable_folds=self.settings.wfo_pass_min_profitable_folds,
            warn_min_profitable_folds=self.settings.wfo_warn_min_profitable_folds,
            pass_min_consecutive_profitable_folds=(
                self.settings.wfo_pass_min_consecutive_profitable_folds
            ),
            warn_min_consecutive_profitable_folds=(
                self.settings.wfo_warn_min_consecutive_profitable_folds
            ),
            min_sharpe_per_fold=self.settings.wfo_min_sharpe_per_fold,
        )
        report.total_wfo_time_sec = total_time
        report.avg_fold_time_sec = total_time / len(folds) if folds else 0.0
        report.avg_trial_time_sec = total_time / total_trials if total_trials else 0.0
        report.compute()

        if print_report:
            self._print_human_report(report)
        return report

    def format_human_report(self, report: WFVReport) -> str:
        """Formats the analyst-facing terminal report for a walk-forward result."""
        return format_human_report(report)

    def _print_human_report(self, report: WFVReport) -> None:
        """Prints the standard walk-forward report."""
        print(self.format_human_report(report))


__all__ = ["FoldResult", "WFVReport", "WalkForwardOptimizer"]

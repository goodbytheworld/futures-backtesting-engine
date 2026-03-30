"""
Optuna-based optimization for event-driven strategies.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Type

import numpy as np
import pandas as pd

from ..engine import BacktestEngine
from ..settings import BacktestSettings
from .objective import objective_score
from .optuna_runtime import (
    HiddenPrints,
    Trial,
    require_optuna,
    restore_optuna_info_verbosity,
    set_optuna_warning_verbosity,
)
from .validation import ValidationException, Validator


class OptunaOptimizer:
    """
    Runs Optuna search against full BacktestEngine evaluations.

    Methodology:
        Each trial copies ``BacktestSettings``, injects candidate parameters,
        executes the real event-driven engine, and scores the resulting metrics
        with the shared optimization objective.
    """

    def __init__(self, settings: Optional[BacktestSettings] = None) -> None:
        """Initializes the optimizer with explicit runtime settings."""
        if settings is None:
            raise ValueError(
                "BacktestSettings must be provided to OptunaOptimizer via Dependency Injection."
            )
        self.settings = settings

    def _validate_search_space(
        self,
        strategy_class: Type,
        search_space: Dict[str, Any],
    ) -> Optional[str]:
        """Validates the strategy search space before any trial allocation."""
        if not search_space:
            return (
                f"{strategy_class.__name__}.get_search_space() returned empty dict. "
                "Nothing to optimize."
            )

        try:
            Validator.validate_params(
                {key: None for key in search_space},
                strategy_class.__name__,
                self.settings.wfo_max_parameters,
            )
        except ValidationException as exc:
            return str(exc)
        return None

    def scale_min_trades_for_window(
        self,
        target_bars: int,
        reference_bars: int,
        base_min_trades: Optional[int] = None,
    ) -> int:
        """Scales a trade floor in proportion to relative sample length."""
        base_threshold = (
            int(base_min_trades)
            if base_min_trades is not None
            else int(self.settings.wfo_prune_min_trades)
        )
        if target_bars <= 0 or reference_bars <= 0:
            return max(1, base_threshold)
        scaled = base_threshold * (float(target_bars) / float(reference_bars))
        return max(1, int(math.ceil(scaled)))

    def _apply_params(
        self,
        trial: Trial,
        search_space: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Samples concrete parameter values from the search-space definition."""
        params: Dict[str, Any] = {}
        for param, bounds in search_space.items():
            if isinstance(bounds, list):
                value = trial.suggest_categorical(param, bounds)
            elif isinstance(bounds, tuple):
                if len(bounds) == 3:
                    start, stop, step = bounds
                    if all(isinstance(v, int) for v in (start, stop, step)):
                        value = trial.suggest_int(param, start, stop, step=step)
                    else:
                        value = trial.suggest_float(
                            param,
                            float(start),
                            float(stop),
                            step=float(step),
                        )
                elif len(bounds) == 2:
                    start, stop = bounds
                    if isinstance(start, int) and isinstance(stop, int):
                        value = trial.suggest_int(param, start, stop)
                    else:
                        value = trial.suggest_float(param, float(start), float(stop))
                else:
                    raise ValueError(
                        f"[OPT] Invalid bounds for param '{param}': {bounds}"
                    )
            else:
                continue
            params[param] = value
        return params

    def _run_strategy(
        self,
        strategy_class: Type,
        params: Dict[str, Any],
        start_date: object = None,
        end_date: object = None,
        data: Optional[pd.DataFrame] = None,
        step_callback: Any = None,
    ) -> Dict[str, Any]:
        """Executes a single strategy run and normalizes the resulting metrics."""
        strategy_settings = self.settings.model_copy(update=params)
        engine = BacktestEngine(
            start_date=start_date,
            end_date=end_date,
            settings=strategy_settings,
            data=data,
        )

        with HiddenPrints():
            engine.run(strategy_class, step_callback=step_callback)

        history = engine.portfolio.get_history_df()
        metrics = engine.analytics.calculate_metrics(history, engine.execution.trades)
        if not metrics:
            return {
                "stats": {
                    "total_trades": 0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "sortino_ratio": 0.0,
                    "calmar_ratio": 0.0,
                    "win_rate": 0.0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                },
                "engine": engine,
            }

        raw_max_drawdown = metrics.get("Max Drawdown", 0.0)
        max_drawdown_pct = (
            raw_max_drawdown * 100 if abs(raw_max_drawdown) <= 1.0 else raw_max_drawdown
        )
        stats = {
            "total_trades": metrics.get("Total Trades", 0),
            "sharpe_ratio": metrics.get("Sharpe Ratio", 0.0),
            "sortino_ratio": metrics.get("Sortino Ratio", 0.0),
            "calmar_ratio": metrics.get("Calmar Ratio", 0.0),
            "max_drawdown": max_drawdown_pct,
            "win_rate": metrics.get("Win Rate", 0.0),
            "avg_win": metrics.get("Avg Win", 0.0),
            "avg_loss": metrics.get("Avg Loss", 0.0),
        }
        return {"stats": stats, "engine": engine}

    def optimize(
        self,
        strategy_class: Type,
        n_trials: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Runs full optimization for a strategy class."""
        optuna = require_optuna()
        n_trials = n_trials or self.settings.wfo_n_trials

        search_space = strategy_class.get_search_space()
        validation_error = self._validate_search_space(strategy_class, search_space)
        if validation_error is not None:
            print(f"[OPT] Validation failed: {validation_error}")
            return {}

        set_optuna_warning_verbosity()
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42),
            pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
            study_name=f"opt_{strategy_class.__name__}",
        )

        print(f"\n[OPT] Optimizing {strategy_class.__name__} for {n_trials} trials...")

        def objective(trial: Trial) -> float:
            def prune_callback(
                engine_ref: Any,
                _current_date: object,
                step: int,
                total: int,
            ) -> None:
                check_interval = max(total // 10, 1)
                if step % check_interval == 0:
                    trial.report(engine_ref.portfolio.total_value, step)
                    if trial.should_prune():
                        raise optuna.TrialPruned("Pruned by Optuna intermediate check")

            params = self._apply_params(trial, search_space)
            stats = self._run_strategy(
                strategy_class,
                params,
                step_callback=prune_callback,
            )["stats"]

            min_trades = self.settings.wfo_prune_min_trades
            max_dd_pct = self.settings.wfo_prune_max_dd_pct
            if stats["total_trades"] < min_trades:
                raise optuna.TrialPruned("Insufficient trades")
            if abs(stats["max_drawdown"]) > max_dd_pct:
                raise optuna.TrialPruned("Excessive Drawdown")
            return objective_score(
                stats,
                min_trades=min_trades,
                target_trades=min_trades * self.settings.wfo_prune_target_trades_mult,
            )

        study.optimize(objective, n_trials=n_trials)
        restore_optuna_info_verbosity()

        print(f"\n{'=' * 60}")
        print(f"OPTIMIZATION RESULTS: {strategy_class.__name__}")
        print(f"{'=' * 60}")
        if not study.best_trials:
            print("[OPT] No trials completed successfully.")
            return {}
        print(f"Best Score:  {study.best_trial.value:.4f}")
        print(f"Best Params: {study.best_params}")
        print(f"{'=' * 60}\n")
        return study.best_params

    def optimize_on_slice(
        self,
        strategy_class: Type,
        start_date: object = None,
        end_date: object = None,
        data: Optional[pd.DataFrame] = None,
        n_trials: Optional[int] = None,
        fold_id: int = 0,
        show_progress_bar: bool = True,
    ) -> Dict[str, Any]:
        """Runs optimization on a bounded slice for walk-forward workflows."""
        optuna = require_optuna()
        n_trials = n_trials or self.settings.wfo_n_trials

        search_space = strategy_class.get_search_space()
        validation_error = self._validate_search_space(strategy_class, search_space)
        if validation_error is not None:
            return {
                "best_params": {},
                "best_score": -1.0,
                "n_trials": 0,
                "trial_std": 0.0,
                "failure_reason": validation_error,
            }

        set_optuna_warning_verbosity()
        study = optuna.create_study(
            study_name=f"wfv_{strategy_class.__name__}_fold{fold_id}",
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42 + fold_id),
        )

        def objective(trial: Trial) -> float:
            params = self._apply_params(trial, search_space)

            def prune_callback(
                engine_ref: Any,
                _current_date: object,
                step: int,
                total: int,
            ) -> None:
                check_interval = max(total // 10, 1)
                if step > 0 and step % check_interval == 0:
                    trial.report(engine_ref.portfolio.total_value, step)
                    if trial.should_prune():
                        raise optuna.TrialPruned("Pruned by WFV Optuna check")

            stats = self._run_strategy(
                strategy_class,
                params,
                start_date=start_date,
                end_date=end_date,
                data=data,
                step_callback=prune_callback,
            )["stats"]
            trial.set_user_attr("stats", stats)

            min_trades = self.settings.wfo_prune_min_trades
            max_dd_pct = self.settings.wfo_prune_max_dd_pct
            if stats["total_trades"] < min_trades:
                raise optuna.TrialPruned("Insufficient trades")
            if abs(stats["max_drawdown"]) > max_dd_pct:
                raise optuna.TrialPruned("Excessive Drawdown")
            return objective_score(
                stats,
                min_trades=min_trades,
                target_trades=min_trades * self.settings.wfo_prune_target_trades_mult,
            )

        study.optimize(
            objective,
            n_trials=n_trials,
            show_progress_bar=show_progress_bar,
        )
        restore_optuna_info_verbosity()

        if not study.best_trials:
            return {
                "best_params": {},
                "best_score": -1.0,
                "n_trials": 0,
                "trial_std": 0.0,
                "failure_reason": "No trials completed successfully.",
            }

        trial_values = [
            trial.value
            for trial in study.trials
            if trial.value is not None
            and trial.state == optuna.trial.TrialState.COMPLETE
        ]
        trial_std = float(np.std(trial_values)) if len(trial_values) > 1 else 0.0
        return {
            "best_params": study.best_params,
            "best_score": study.best_trial.value,
            "n_trials": len(study.trials),
            "trial_std": trial_std,
            "best_stats": study.best_trial.user_attrs.get("stats", {}),
        }

    def evaluate_on_slice(
        self,
        strategy_class: Type,
        params: Dict[str, Any],
        start_date: object = None,
        end_date: object = None,
        data: Optional[pd.DataFrame] = None,
        min_trades_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Evaluates fixed parameters on an OOS slice."""
        stats = self._run_strategy(
            strategy_class,
            params,
            start_date=start_date,
            end_date=end_date,
            data=data,
        )["stats"]

        min_trades = (
            int(min_trades_override)
            if min_trades_override is not None
            else int(self.settings.wfo_prune_min_trades)
        )
        score = objective_score(
            stats,
            min_trades=min_trades,
            target_trades=min_trades * self.settings.wfo_prune_target_trades_mult,
        )
        rejection_reason: Optional[str] = None
        if stats["total_trades"] < min_trades:
            rejection_reason = (
                f"Insufficient OOS trades: {stats['total_trades']} < {min_trades}"
            )
        return {"stats": stats, "score": score, "rejection_reason": rejection_reason}

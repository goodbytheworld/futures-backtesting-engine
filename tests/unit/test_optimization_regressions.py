from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.backtest_engine.optimization.fold_generator import PurgedFoldGenerator
from src.backtest_engine.optimization.objective import objective_score
from src.backtest_engine.optimization.optimizer import OptunaOptimizer
from src.backtest_engine.optimization.wfv_optimizer import WalkForwardOptimizer
from src.backtest_engine.optimization.wfv_optimizer import WFVReport
from src.backtest_engine.optimization.wfv_optimizer import FoldResult
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


def test_purged_fold_generator_keeps_test_window_intact_when_embargo_is_set() -> None:
    """
    Embargo must reduce train history, not consume the left side of OOS samples.
    """
    data = pd.DataFrame({"close": range(100)})
    splitter = PurgedFoldGenerator(
        n_folds=2,
        test_size=0.1,
        purge_bars=2,
        embargo_bars=3,
    )

    folds = list(splitter.split(data))
    _, first_test_idx = folds[0]

    assert len(first_test_idx) == 10
    assert first_test_idx[0] == 80


def test_fold_degradation_marks_non_positive_is_scores_as_failure() -> None:
    """
    Negative/zero IS scores should not be treated as neutral degradation.
    """
    fold = FoldResult(
        fold_id=1,
        train_start="2024-01-01",
        train_end="2024-03-01",
        test_start="2024-03-02",
        test_end="2024-04-01",
        best_params={},
        is_score=-1.0,
        oos_score=0.2,
        n_trials=0,
        trial_std=0.0,
        oos_stats={},
    )

    assert fold.degradation == -1.0


def test_fold_win_rate_drift_and_expected_value_helpers() -> None:
    """
    Fold helper properties should expose WR drift and EV for IS/OOS diagnostics.
    """
    fold = FoldResult(
        fold_id=1,
        train_start="2024-01-01",
        train_end="2024-03-01",
        test_start="2024-03-02",
        test_end="2024-04-01",
        best_params={},
        is_score=1.0,
        oos_score=0.8,
        n_trials=10,
        trial_std=0.2,
        is_stats={"win_rate": 0.60},
        oos_stats={"win_rate": 0.48, "avg_win": 2.0, "avg_loss": -1.0},
    )

    assert round(fold.win_rate_degradation, 4) == -0.2
    assert round(fold.oos_expected_value, 4) == 0.44


def test_failed_fold_disables_wr_drift_and_ev_helpers() -> None:
    """
    Failed IS folds should not contribute misleading WR drift or EV signals.
    """
    fold = FoldResult(
        fold_id=1,
        train_start="2024-01-01",
        train_end="2024-03-01",
        test_start="2024-03-02",
        test_end="2024-04-01",
        best_params={},
        is_score=0.0,
        oos_score=0.0,
        n_trials=1,
        trial_std=0.0,
        is_stats={"win_rate": 0.43},
        oos_stats={"win_rate": 0.46, "avg_win": 2.0, "avg_loss": -1.0},
    )

    assert fold.is_failed is True
    assert fold.win_rate_degradation == 0.0
    assert fold.oos_expected_value == 0.0


def test_objective_score_returns_hard_rejection_for_too_few_trades() -> None:
    """
    A trade-starved run should return an explicit hard rejection score.
    """
    score = objective_score(
        {
            "total_trades": 0,
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.0,
            "max_drawdown": -10.0,
        },
        min_trades=10,
    )

    assert score == -1.0


def test_objective_score_handles_zero_target_trades_without_division_error() -> None:
    """
    Activity penalty path should be safe even if target_trades is misconfigured.
    """
    score = objective_score(
        {
            "total_trades": 10,
            "sharpe_ratio": 1.0,
            "sortino_ratio": 1.0,
            "max_drawdown": -10.0,
        },
        min_trades=1,
        target_trades=0,
    )

    assert score >= 0.0


@dataclass
class _DummySettings:
    alpha: int = 1

    def model_copy(self, update):
        merged = {"alpha": self.alpha, **update}
        return _DummySettings(**merged)


def _build_wfo_execution_data() -> pd.DataFrame:
    """
    Builds a minimal deterministic dataset for WFO execution-cost regressions.
    """

    index = pd.date_range("2024-01-01 09:30:00", periods=3, freq="1h")
    return pd.DataFrame(
        {
            "open": [100.0, 100.0, 103.0],
            "high": [100.5, 106.0, 103.5],
            "low": [99.5, 99.0, 102.5],
            "close": [100.0, 102.0, 103.0],
            "volume": [1_000.0, 1_000.0, 1_000.0],
        },
        index=index,
    )


def _build_wfo_settings() -> BacktestSettings:
    """
    Returns shared settings for WFO execution-cost regressions.
    """

    settings = BacktestSettings(
        default_symbol="TEST",
        initial_capital=10_000.0,
        commission_rate=2.5,
        spread_ticks=2,
        spread_mode="static",
        use_trading_hours=False,
        wfo_prune_min_trades=1,
    )
    settings.instrument_specs = {
        "TEST": {
            "tick_size": 0.25,
            "multiplier": 50.0,
            "margin_ratio": 0.10,
        }
    }
    return settings


class _WFOLimitEntryStrategy(BaseStrategy):
    """
    Emits one LIMIT entry and one MARKET exit for WFO execution-path tests.
    """

    def __init__(self, engine: object) -> None:
        super().__init__(engine)
        self.entry_sent = False
        self.exit_sent = False

    def on_bar(self, bar: pd.Series) -> list:
        if not self.entry_sent:
            self.entry_sent = True
            return [self.limit_order("BUY", 1, limit_price=100.0, reason="SIGNAL")]
        if not self.exit_sent and not self.is_flat():
            self.exit_sent = True
            return [self.market_order("SELL", 1, reason="EXIT")]
        return []


class _WFOStopLimitEntryStrategy(BaseStrategy):
    """
    Emits one STOP_LIMIT entry and one MARKET exit for WFO execution-path tests.
    """

    def __init__(self, engine: object) -> None:
        super().__init__(engine)
        self.entry_sent = False
        self.exit_sent = False

    def on_bar(self, bar: pd.Series) -> list:
        if not self.entry_sent:
            self.entry_sent = True
            return [
                self.stop_limit_order(
                    "BUY",
                    1,
                    stop_price=105.0,
                    limit_price=101.0,
                    reason="SIGNAL",
                )
            ]
        if not self.exit_sent and not self.is_flat():
            self.exit_sent = True
            return [self.market_order("SELL", 1, reason="EXIT")]
        return []


def test_optimizer_normalizes_max_drawdown_to_percent(monkeypatch) -> None:
    """
    MaxDD input should end up in percent regardless of source convention.
    """

    class _FakeAnalytics:
        def calculate_metrics(self, history, trades):
            return {
                "Total Trades": 5,
                "Sharpe Ratio": 1.0,
                "Sortino Ratio": 1.1,
                "Calmar Ratio": 0.8,
                "Max Drawdown": -25.0,  # already in percent
            }

    class _FakePortfolio:
        def get_history_df(self):
            return pd.DataFrame({"total_value": [100_000.0, 99_000.0]})

    class _FakeEngine:
        def __init__(self, *args, **kwargs):
            self.analytics = _FakeAnalytics()
            self.portfolio = _FakePortfolio()
            self.execution = type("_Exec", (), {"trades": []})()

        def run(self, strategy_class, step_callback=None):
            return None

    monkeypatch.setattr(
        "src.backtest_engine.optimization.optimizer.BacktestEngine",
        _FakeEngine,
    )

    optimizer = OptunaOptimizer(settings=_DummySettings())
    result = optimizer._run_strategy(strategy_class=object, params={})

    assert result["stats"]["max_drawdown"] == -25.0


def test_wfo_optimizer_limit_entry_uses_shared_limit_cost_profile() -> None:
    """
    WFO engine runs must inherit the shared LIMIT execution-cost semantics.

    Methodology:
        OptunaOptimizer._run_strategy is the concrete engine path used by
        optimize_on_slice/evaluate_on_slice, so this regression proves the WFO
        workflow inherits the same order-type friction behavior as normal
        single-backtest execution.
    """

    optimizer = OptunaOptimizer(settings=_build_wfo_settings())
    result = optimizer._run_strategy(
        strategy_class=_WFOLimitEntryStrategy,
        params={},
        data=_build_wfo_execution_data(),
    )

    trades = result["engine"].execution.trades

    assert len(trades) == 1
    assert trades[0].entry_price == 100.0
    assert trades[0].slippage == 25.0
    assert trades[0].commission == 5.0


def test_wfo_optimizer_stop_limit_entry_uses_shared_stop_limit_cost_profile() -> None:
    """
    WFO engine runs must treat STOP_LIMIT as limit-like by default.
    """

    optimizer = OptunaOptimizer(settings=_build_wfo_settings())
    result = optimizer._run_strategy(
        strategy_class=_WFOStopLimitEntryStrategy,
        params={},
        data=_build_wfo_execution_data(),
    )

    trades = result["engine"].execution.trades

    assert len(trades) == 1
    assert trades[0].entry_price == 101.0
    assert trades[0].slippage == 25.0
    assert trades[0].commission == 5.0


def test_purged_fold_generator_rejects_zero_fold_size() -> None:
    """
    Tiny test_size values should fail fast instead of creating range(step=0).
    """
    data = pd.DataFrame({"close": range(10)})
    splitter = PurgedFoldGenerator(n_folds=2, test_size=0.01)

    try:
        list(splitter.split(data))
    except ValueError as exc:
        assert "Fold size became zero" in str(exc)
    else:
        raise AssertionError("Expected ValueError for zero fold size")


def test_wfv_skips_oos_evaluation_when_is_optimization_fails(monkeypatch) -> None:
    """
    If IS optimization has no successful trials, OOS must not run on empty params.
    """
    settings = BacktestSettings(wfo_n_folds=1, wfo_test_size_pct=0.2, wfo_n_trials=1)
    wfo = WalkForwardOptimizer(settings=settings)
    data = pd.DataFrame(
        {"close": range(30)},
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )

    monkeypatch.setattr(wfo.data_lake, "load", lambda symbol, timeframe: data)
    monkeypatch.setattr(
        wfo.base_optimizer,
        "optimize_on_slice",
        lambda **kwargs: {
            "best_params": {},
            "best_score": -1.0,
            "n_trials": 0,
            "trial_std": 0.0,
        },
    )

    def _must_not_be_called(**kwargs):
        raise AssertionError("evaluate_on_slice must not be called for failed IS optimization")

    monkeypatch.setattr(wfo.base_optimizer, "evaluate_on_slice", _must_not_be_called)

    class _Strategy:
        @staticmethod
        def get_search_space():
            return {}

    report = wfo.run(
        strategy_class=_Strategy,
        verbose=False,
        print_report=False,
        show_progress_bar=False,
    )

    assert report.fold_results
    assert report.fold_results[0].is_score == -1.0
    assert report.fold_results[0].oos_score == -1.0


def test_wfv_skips_oos_evaluation_when_is_score_is_zero(monkeypatch) -> None:
    """
    Zero IS score should be treated as failed quality and skip OOS evaluation.
    """
    settings = BacktestSettings(wfo_n_folds=1, wfo_test_size_pct=0.2, wfo_n_trials=1)
    wfo = WalkForwardOptimizer(settings=settings)
    data = pd.DataFrame(
        {"close": range(30)},
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )

    monkeypatch.setattr(wfo.data_lake, "load", lambda symbol, timeframe: data)
    monkeypatch.setattr(
        wfo.base_optimizer,
        "optimize_on_slice",
        lambda **kwargs: {
            "best_params": {"x": 1},
            "best_score": 0.0,
            "n_trials": 1,
            "trial_std": 0.0,
            "best_stats": {"win_rate": 0.5},
        },
    )

    def _must_not_be_called(**kwargs):
        raise AssertionError("evaluate_on_slice must not be called for zero IS score")

    monkeypatch.setattr(wfo.base_optimizer, "evaluate_on_slice", _must_not_be_called)

    class _Strategy:
        @staticmethod
        def get_search_space():
            return {}

    report = wfo.run(
        strategy_class=_Strategy,
        verbose=False,
        print_report=False,
        show_progress_bar=False,
    )

    assert report.fold_results[0].oos_score == -1.0


def test_wfv_report_adds_warning_on_large_win_rate_drift() -> None:
    """
    Report should surface a WR drift warning when IS->OOS drop is materially large.
    """
    folds = [
        FoldResult(
            fold_id=1,
            train_start="2024-01-01",
            train_end="2024-03-01",
            test_start="2024-03-02",
            test_end="2024-04-01",
            best_params={},
            is_score=1.0,
            oos_score=0.5,
            n_trials=10,
            trial_std=0.2,
            is_stats={"win_rate": 0.60},
            oos_stats={"win_rate": 0.45, "avg_win": 1.0, "avg_loss": -1.0},
        )
    ]
    report = WFVReport(symbol="ES", strategy_name="S", n_folds=1, fold_results=folds)
    report.compute()

    assert any("WinRate Drift" in warning for warning in report.warnings)


def test_wfv_report_requires_consecutive_profitable_folds_for_pass() -> None:
    """
    PASS should fail if profitable folds are not consecutive under consistency gates.
    """
    folds = [
        FoldResult(
            fold_id=1,
            train_start="2024-01-01",
            train_end="2024-02-01",
            test_start="2024-02-02",
            test_end="2024-03-01",
            best_params={},
            is_score=1.0,
            oos_score=0.5,
            n_trials=20,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": 1.0},
        ),
        FoldResult(
            fold_id=2,
            train_start="2024-02-01",
            train_end="2024-03-01",
            test_start="2024-03-02",
            test_end="2024-04-01",
            best_params={},
            is_score=1.0,
            oos_score=-0.2,
            n_trials=20,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": -0.3},
        ),
        FoldResult(
            fold_id=3,
            train_start="2024-03-01",
            train_end="2024-04-01",
            test_start="2024-04-02",
            test_end="2024-05-01",
            best_params={},
            is_score=1.0,
            oos_score=0.4,
            n_trials=20,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": 1.1},
        ),
    ]
    report = WFVReport(
        symbol="ES",
        strategy_name="S",
        n_folds=3,
        fold_results=folds,
        pass_min_profitable_folds=2,
        pass_min_consecutive_profitable_folds=2,
    )
    report.compute()

    assert report.verdict != "PASS"


def test_wfv_report_applies_per_fold_sharpe_threshold() -> None:
    """
    Fold quality count must respect configured minimum Sharpe threshold.
    """
    folds = [
        FoldResult(
            fold_id=1,
            train_start="2024-01-01",
            train_end="2024-02-01",
            test_start="2024-02-02",
            test_end="2024-03-01",
            best_params={},
            is_score=1.0,
            oos_score=0.6,
            n_trials=20,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": 0.2},
        ),
        FoldResult(
            fold_id=2,
            train_start="2024-02-01",
            train_end="2024-03-01",
            test_start="2024-03-02",
            test_end="2024-04-01",
            best_params={},
            is_score=1.0,
            oos_score=0.5,
            n_trials=20,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": 0.8},
        ),
    ]
    report = WFVReport(
        symbol="ES",
        strategy_name="S",
        n_folds=2,
        fold_results=folds,
        pass_min_profitable_folds=2,
        warn_min_profitable_folds=2,
        min_sharpe_per_fold=0.5,
    )
    report.compute()

    assert report.verdict == "FAIL"


def test_wfv_report_uses_single_profitable_fold_for_candidate_params() -> None:
    """
    A lone profitable fold should not mix its params with losing folds.
    """
    folds = [
        FoldResult(
            fold_id=1,
            train_start="2024-01-01",
            train_end="2024-02-01",
            test_start="2024-02-02",
            test_end="2024-03-01",
            best_params={"length": 10, "mode": "fast"},
            is_score=1.0,
            oos_score=0.7,
            n_trials=10,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": 1.0},
        ),
        FoldResult(
            fold_id=2,
            train_start="2024-02-01",
            train_end="2024-03-01",
            test_start="2024-03-02",
            test_end="2024-04-01",
            best_params={"length": 100, "mode": "slow"},
            is_score=1.0,
            oos_score=-1.0,
            n_trials=10,
            trial_std=0.1,
            oos_stats={"sharpe_ratio": -1.0},
        ),
    ]
    report = WFVReport(symbol="ES", strategy_name="S", n_folds=2, fold_results=folds)
    report.compute()

    assert report.candidate_params == {"length": 10, "mode": "fast"}


def test_scale_min_trades_for_window_scales_by_relative_sample_size() -> None:
    """
    OOS trade floors should scale with bar-count ratio instead of staying fixed.
    """
    optimizer = OptunaOptimizer(settings=BacktestSettings(wfo_prune_min_trades=40))

    assert optimizer.scale_min_trades_for_window(target_bars=20, reference_bars=100) == 8


def test_evaluate_on_slice_uses_scaled_trade_floor_override(monkeypatch) -> None:
    """
    Shorter OOS windows should be scored against the overridden trade floor.
    """
    optimizer = OptunaOptimizer(settings=BacktestSettings(wfo_prune_min_trades=40))

    monkeypatch.setattr(
        optimizer,
        "_run_strategy",
        lambda *args, **kwargs: {
            "stats": {
                "total_trades": 15,
                "sharpe_ratio": 1.0,
                "sortino_ratio": 1.0,
                "max_drawdown": -5.0,
                "win_rate": 0.5,
                "avg_win": 1.0,
                "avg_loss": -1.0,
            }
        },
    )

    accepted = optimizer.evaluate_on_slice(
        strategy_class=object,
        params={},
        min_trades_override=10,
    )
    rejected = optimizer.evaluate_on_slice(
        strategy_class=object,
        params={},
        min_trades_override=20,
    )

    assert accepted["score"] >= 0.0
    assert accepted["rejection_reason"] is None
    assert rejected["score"] == -1.0
    assert "Insufficient OOS trades" in str(rejected["rejection_reason"])


def test_optimize_on_slice_fails_fast_when_search_space_is_empty() -> None:
    """
    WFV should surface empty search spaces before creating trials.
    """

    class _Strategy:
        @staticmethod
        def get_search_space():
            return {}

    optimizer = OptunaOptimizer(settings=BacktestSettings())
    result = optimizer.optimize_on_slice(
        strategy_class=_Strategy,
        n_trials=1,
        show_progress_bar=False,
    )

    assert result["best_score"] == -1.0
    assert "empty dict" in result["failure_reason"]


def test_wfv_scales_oos_trade_floor_before_evaluation(monkeypatch) -> None:
    """
    Walk-forward evaluation should pass a bar-length-scaled OOS trade floor.
    """

    class _Strategy:
        @staticmethod
        def get_search_space():
            return {}

    settings = BacktestSettings(
        wfo_n_folds=1,
        wfo_test_size_pct=0.2,
        wfo_n_trials=1,
        wfo_prune_min_trades=40,
    )
    wfo = WalkForwardOptimizer(settings=settings)
    data = pd.DataFrame(
        {"close": range(30)},
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )
    seen: dict[str, int] = {}

    monkeypatch.setattr(wfo.data_lake, "load", lambda symbol, timeframe: data)
    monkeypatch.setattr(
        wfo.base_optimizer,
        "optimize_on_slice",
        lambda **kwargs: {
            "best_params": {"x": 1},
            "best_score": 1.0,
            "n_trials": 1,
            "trial_std": 0.0,
            "best_stats": {"win_rate": 0.5},
        },
    )

    def _fake_eval(**kwargs):
        seen["min_trades_override"] = kwargs["min_trades_override"]
        return {"score": 0.5, "stats": {"sharpe_ratio": 1.0}, "rejection_reason": None}

    monkeypatch.setattr(wfo.base_optimizer, "evaluate_on_slice", _fake_eval)

    wfo.run(
        strategy_class=_Strategy,
        verbose=False,
        print_report=False,
        show_progress_bar=False,
    )

    assert seen["min_trades_override"] == 10

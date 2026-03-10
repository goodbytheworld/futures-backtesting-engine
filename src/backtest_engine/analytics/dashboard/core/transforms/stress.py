from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from src.backtest_engine.analytics.dashboard.risk_analysis.models import StressMultipliers, StressScenarioResult
from .risk import compute_var_es_metrics, compute_drawdown_series, compute_annualised_sharpe

def _build_trade_cost_series(
    trades_df: Optional[pd.DataFrame],
    instrument_specs: Dict[str, Dict[str, float]],
) -> tuple[pd.Series, pd.Series]:
    """Aggregates daily commission and slippage costs from trade records."""
    if trades_df is None or trades_df.empty or "exit_time" not in trades_df.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    df = trades_df.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")
    df = df.dropna(subset=["exit_time"])
    if df.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    daily_index = df["exit_time"].dt.normalize()
    commission_daily = (
        df.groupby(daily_index)["commission"].sum().astype(float)
        if "commission" in df.columns
        else pd.Series(dtype=float)
    )

    if "slippage" in df.columns:
        multiplier_s = df["symbol"].map(
            lambda symbol: float(instrument_specs.get(str(symbol), {}).get("multiplier", 1.0))
        )
        quantity_s = df["quantity"].abs().fillna(0.0) if "quantity" in df.columns else 0.0
        slippage_cost = df["slippage"].abs().fillna(0.0) * quantity_s * multiplier_s
        slippage_daily = slippage_cost.groupby(daily_index).sum().astype(float)
    else:
        slippage_daily = pd.Series(dtype=float)

    return commission_daily, slippage_daily

def _align_series_to_index(series: pd.Series, index: pd.Index) -> pd.Series:
    """Reindexes a numeric series to a target index with zero fill."""
    if series is None or series.empty:
        return pd.Series(0.0, index=index)
    return series.reindex(index, fill_value=0.0).astype(float)

def _build_equity_from_daily_pnl(initial_equity: float, daily_pnl: pd.Series) -> pd.Series:
    """Reconstructs a daily equity curve from initial equity and daily PnL."""
    if daily_pnl is None or daily_pnl.empty:
        return pd.Series(dtype=float)
    return pd.Series(initial_equity + daily_pnl.astype(float).cumsum(), index=daily_pnl.index)

def _build_scenario_metrics(
    equity: pd.Series,
    daily_pnl: pd.Series,
    primary_confidence: float,
    tail_confidence: float,
    risk_free_rate: float,
) -> Dict[str, float]:
    """Computes comparable summary metrics for a baseline or stressed path."""
    var_metrics = compute_var_es_metrics(daily_pnl, primary_confidence, tail_confidence)
    drawdown = compute_drawdown_series(equity)
    daily_returns = equity.pct_change(fill_method=None).dropna() if not equity.empty else pd.Series(dtype=float)
    sharpe = compute_annualised_sharpe(daily_returns, risk_free_rate=risk_free_rate)

    return {
        "final_pnl": float(daily_pnl.sum()),
        "end_equity": float(equity.iloc[-1]) if not equity.empty else float("nan"),
        "var_primary": var_metrics["var_primary"],
        "es_primary": var_metrics["es_primary"],
        "var_tail": var_metrics["var_tail"],
        "es_tail": var_metrics["es_tail"],
        "max_drawdown_pct": abs(float(drawdown.min())) if not drawdown.empty else float("nan"),
        "sharpe": sharpe,
    }

def compute_stress_scenarios(
    daily_equity: pd.Series,
    daily_pnl: pd.Series,
    trades_df: Optional[pd.DataFrame],
    instrument_specs: Dict[str, Dict[str, float]],
    stress_multipliers: StressMultipliers,
    primary_confidence: float,
    tail_confidence: float,
    risk_free_rate: float = 0.0,
) -> List[StressScenarioResult]:
    """
    Builds baseline and stressed risk scenarios from the realised daily PnL path.

    Methodology:
        Volatility stress scales the demeaned daily PnL path, preserving the
        realised average drift while amplifying dispersion. Slippage and
        commission stresses add only the incremental trading cost above the
        realised baseline so the scenario remains anchored to the original run.
    """
    if daily_equity is None or daily_equity.dropna().empty or daily_pnl is None or daily_pnl.empty:
        return []

    clean_equity = daily_equity.dropna().astype(float)
    clean_pnl = daily_pnl.reindex(clean_equity.index, fill_value=0.0).astype(float)
    initial_equity = float(clean_equity.iloc[0])

    commission_daily, slippage_daily = _build_trade_cost_series(trades_df, instrument_specs)
    commission_daily = _align_series_to_index(commission_daily, clean_pnl.index)
    slippage_daily = _align_series_to_index(slippage_daily, clean_pnl.index)

    mean_pnl = float(clean_pnl.mean())
    centered_pnl = clean_pnl - mean_pnl

    extra_commission = commission_daily * max(stress_multipliers.commission - 1.0, 0.0)
    extra_slippage = slippage_daily * max(stress_multipliers.slippage - 1.0, 0.0)

    scenario_map = {
        "baseline": clean_pnl,
        "volatility": mean_pnl + centered_pnl * stress_multipliers.volatility,
        "slippage": clean_pnl - extra_slippage,
        "commission": clean_pnl - extra_commission,
        "combined": mean_pnl + centered_pnl * stress_multipliers.volatility - extra_slippage - extra_commission,
    }
    scenario_labels = {
        "baseline": "Baseline",
        "volatility": f"Volatility x{stress_multipliers.volatility:.1f}",
        "slippage": f"Slippage x{stress_multipliers.slippage:.1f}",
        "commission": f"Commission x{stress_multipliers.commission:.1f}",
        "combined": "Combined shock",
    }

    baseline_final_pnl = float(clean_pnl.sum())
    results: List[StressScenarioResult] = []
    for name, scenario_pnl in scenario_map.items():
        scenario_equity = _build_equity_from_daily_pnl(initial_equity, scenario_pnl)
        scenario_metrics = _build_scenario_metrics(
            scenario_equity,
            scenario_pnl,
            primary_confidence=primary_confidence,
            tail_confidence=tail_confidence,
            risk_free_rate=risk_free_rate,
        )
        results.append(
            StressScenarioResult(
                name=name,
                label=scenario_labels[name],
                equity=scenario_equity,
                daily_pnl=scenario_pnl,
                metrics=scenario_metrics,
                pnl_delta=float(scenario_metrics["final_pnl"] - baseline_final_pnl),
            )
        )

    return results


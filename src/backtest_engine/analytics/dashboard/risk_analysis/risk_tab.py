"""
Risk Analysis tab renderer.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

from src.backtest_engine.analytics.dashboard.core.data_layer import ResultBundle
from src.backtest_engine.analytics.dashboard.core.transforms import (
    build_risk_profile,
    build_strategy_equity_curve,
)
from src.backtest_engine.analytics.dashboard.risk_analysis.charts import (
    build_drawdown_curve_figure,
    build_drawdown_distribution_figure,
    build_equity_curve_figure,
    build_risk_distribution_figure,
    build_rolling_volatility_figure,
    build_stress_test_figure,
    build_var_es_figure,
)
from src.backtest_engine.analytics.dashboard.risk_analysis.models import (
    RiskDashboardConfig,
    RiskProfile,
    StressMultipliers,
)


def _fmt_currency(value: float) -> str:
    """Formats a dollar value for dashboard metrics."""
    if pd.isna(value):
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _fmt_pct(value: float) -> str:
    """Formats a percentage value for dashboard metrics."""
    if pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"


def _fmt_days(value: float) -> str:
    """Formats a duration in days for dashboard metrics."""
    if pd.isna(value):
        return "N/A"
    return f"{value:.1f}d"


def _render_stress_controls(key_prefix: str, config: RiskDashboardConfig) -> StressMultipliers:
    """Renders stress-test sliders and returns the selected multipliers."""
    st.markdown("##### Stress Tests")
    st.caption(
        "Volatility shock scales demeaned daily PnL dispersion. "
        "Slippage and commission shocks add only incremental trading costs above the realised baseline."
    )
    col_container, _ = st.columns([2, 1])
    with col_container:
        col_vol, col_slip, col_comm = st.columns(3)
    with col_vol:
        volatility = st.slider(
            "Volatility x",
            min_value=float(config.stress_slider_min),
            max_value=float(config.stress_slider_max),
            value=float(config.stress_defaults.volatility),
            step=float(config.stress_slider_step),
            key=f"{key_prefix}_stress_volatility",
        )
    with col_slip:
        slippage = st.slider(
            "Slippage x",
            min_value=float(config.stress_slider_min),
            max_value=float(config.stress_slider_max),
            value=float(config.stress_defaults.slippage),
            step=float(config.stress_slider_step),
            key=f"{key_prefix}_stress_slippage",
        )
    with col_comm:
        commission = st.slider(
            "Commission x",
            min_value=float(config.stress_slider_min),
            max_value=float(config.stress_slider_max),
            value=float(config.stress_defaults.commission),
            step=float(config.stress_slider_step),
            key=f"{key_prefix}_stress_commission",
        )

    return StressMultipliers(
        volatility=float(volatility),
        slippage=float(slippage),
        commission=float(commission),
    )


def _render_summary_cards(profile: RiskProfile, config: RiskDashboardConfig) -> None:
    """Renders top-level scalar risk metrics."""
    summary = profile.summary
    conf_primary = int(config.var_confidence_primary * 100)
    conf_tail = int(config.var_confidence_tail * 100)

    row_1 = st.columns(4)
    row_1[0].metric(f"VaR {conf_primary}", _fmt_currency(summary.get("var_primary", float("nan"))))
    row_1[1].metric(f"VaR {conf_tail}", _fmt_currency(summary.get("var_tail", float("nan"))))
    row_1[2].metric(f"ES {conf_primary}", _fmt_currency(summary.get("es_primary", float("nan"))))
    row_1[3].metric(f"ES {conf_tail}", _fmt_currency(summary.get("es_tail", float("nan"))))

    row_2 = st.columns(4)
    row_2[0].metric("Max DD", _fmt_pct(summary.get("max_drawdown_pct", float("nan"))))
    row_2[1].metric("DD 95", _fmt_pct(summary.get("drawdown_95_pct", float("nan"))))
    row_2[2].metric("Max DD Duration", _fmt_days(summary.get("max_drawdown_duration_days", float("nan"))))
    row_2[3].metric("Latest Vol", _fmt_pct(summary.get("latest_vol_pct", float("nan"))))


def _render_stress_table(profile: RiskProfile, config: RiskDashboardConfig) -> None:
    """Renders the stress-test summary table."""
    if not profile.stress_results:
        st.info("No stress scenarios available.")
        return

    primary_label = int(config.var_confidence_primary * 100)
    rows = []
    for scenario in profile.stress_results:
        rows.append(
            {
                "Scenario": scenario.label,
                "Final PnL": _fmt_currency(scenario.metrics.get("final_pnl", float("nan"))),
                "Delta vs Base": _fmt_currency(scenario.pnl_delta),
                f"VaR {primary_label}": _fmt_currency(scenario.metrics.get("var_primary", float("nan"))),
                f"ES {primary_label}": _fmt_currency(scenario.metrics.get("es_primary", float("nan"))),
                "Max DD": _fmt_pct(scenario.metrics.get("max_drawdown_pct", float("nan"))),
                "Sharpe": (
                    f"{scenario.metrics['sharpe']:.2f}"
                    if not pd.isna(scenario.metrics.get("sharpe", float("nan")))
                    else "N/A"
                ),
            }
        )

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_risk_profile_core(profile: RiskProfile, config: RiskDashboardConfig) -> None:
    """Renders charts and summary blocks except stress tests."""
    _render_summary_cards(profile, config)

    st.markdown("##### Tail Risk")
    col_var, col_dist = st.columns(2)
    with col_var:
        st.plotly_chart(
            build_var_es_figure(
                profile.rolling_var,
                primary_confidence=config.var_confidence_primary,
                tail_confidence=config.var_confidence_tail,
                title="Rolling Historical VaR / ES",
            ),
            use_container_width=True,
        )
    with col_dist:
        st.plotly_chart(
            build_risk_distribution_figure(
                profile.daily_pnl,
                profile.summary,
                primary_confidence=config.var_confidence_primary,
                tail_confidence=config.var_confidence_tail,
                title="Daily PnL Tail Distribution",
            ),
            use_container_width=True,
        )

    st.markdown("##### Drawdown Analysis")
    col_eq, col_dd = st.columns(2)
    with col_eq:
        st.plotly_chart(
            build_equity_curve_figure(profile.equity, title="Equity Curve"),
            use_container_width=True,
        )
    with col_dd:
        st.plotly_chart(
            build_drawdown_curve_figure(profile.drawdown, title="Drawdown Curve"),
            use_container_width=True,
        )

    col_dd_dist, col_vol = st.columns(2)
    with col_dd_dist:
        st.plotly_chart(
            build_drawdown_distribution_figure(
                profile.drawdown_episodes,
                title="Drawdown Distribution",
            ),
            use_container_width=True,
        )
    with col_vol:
        st.plotly_chart(
            build_rolling_volatility_figure(
                profile.rolling_vol,
                title="Rolling Volatility (Annualized Returns)",
            ),
            use_container_width=True,
        )


def _render_stress_analysis(profile: RiskProfile, config: RiskDashboardConfig) -> None:
    """Renders the stress test charts and table."""
    st.plotly_chart(
        build_stress_test_figure(profile.stress_results, title="Stressed Equity Paths"),
        use_container_width=True,
    )
    _render_stress_table(profile, config)


def _build_strategy_profiles(
    bundle: ResultBundle,
    config: RiskDashboardConfig,
    instrument_specs: Dict[str, Dict[str, float]],
    risk_free_rate: float,
) -> Dict[str, RiskProfile]:
    """Builds baseline strategy risk profiles for the portfolio strategy table."""
    profiles: Dict[str, RiskProfile] = {}
    strategy_count = len(bundle.slots or {})
    for slot_id, strategy_name in (bundle.slots or {}).items():
        strategy_equity = build_strategy_equity_curve(
            bundle.history,
            slot_id=str(slot_id),
            slot_weight=float(bundle.slot_weights.get(slot_id)) if bundle.slot_weights and slot_id in bundle.slot_weights else None,
            slot_count=strategy_count,
        )
        strategy_trades = (
            bundle.trades[bundle.trades["strategy"] == strategy_name]
            if bundle.trades is not None and not bundle.trades.empty and "strategy" in bundle.trades.columns
            else pd.DataFrame()
        )
        profiles[strategy_name] = build_risk_profile(
            label=strategy_name,
            equity=strategy_equity,
            trades_df=strategy_trades,
            instrument_specs=instrument_specs,
            primary_confidence=config.var_confidence_primary,
            tail_confidence=config.var_confidence_tail,
            rolling_var_window_days=config.rolling_var_window_days,
            rolling_vol_windows=config.rolling_vol_windows,
            stress_multipliers=config.stress_defaults,
            risk_free_rate=risk_free_rate,
        )
    return profiles


def _render_strategy_snapshot_table(
    strategy_profiles: Dict[str, RiskProfile],
    config: RiskDashboardConfig,
) -> None:
    """Renders a compact cross-strategy risk summary for portfolio mode."""
    if not strategy_profiles:
        st.info("No strategy-level risk profiles available.")
        return

    primary_label = int(config.var_confidence_primary * 100)
    rows = []
    for strategy_name, profile in strategy_profiles.items():
        rows.append(
            {
                "Strategy": strategy_name,
                f"VaR {primary_label}": _fmt_currency(profile.summary.get("var_primary", float("nan"))),
                f"ES {primary_label}": _fmt_currency(profile.summary.get("es_primary", float("nan"))),
                "Max DD": _fmt_pct(profile.summary.get("max_drawdown_pct", float("nan"))),
                "DD 95": _fmt_pct(profile.summary.get("drawdown_95_pct", float("nan"))),
                "Latest Vol": _fmt_pct(profile.summary.get("latest_vol_pct", float("nan"))),
                "Sharpe": (
                    f"{profile.summary['sharpe']:.2f}"
                    if not pd.isna(profile.summary.get("sharpe", float("nan")))
                    else "N/A"
                ),
            }
        )

    table = pd.DataFrame(rows).sort_values(by="Strategy")
    st.dataframe(table, hide_index=True, use_container_width=True)


def render_risk_tab(
    bundle: ResultBundle,
    config: RiskDashboardConfig,
    instrument_specs: Dict[str, Dict[str, float]],
    risk_free_rate: float,
) -> None:
    """
    Renders the Risk Analysis tab.

    Methodology:
        Portfolio aggregate and per-strategy drilldown are rendered as separate
        sections because strategy views must not inherit portfolio-only effects
        such as diversification and cross-strategy netting.
    """
    if bundle is None or bundle.history is None or bundle.history.empty:
        st.info("No backtest history available for risk analysis.")
        return

    if bundle.run_type == "portfolio":
        st.markdown("#### Portfolio Risk")
        st.caption(
            "This section uses aggregate portfolio equity. Risk metrics here include diversification, "
            "netting and cross-strategy path interactions."
        )
        portfolio_top = st.container()
        portfolio_stress = _render_stress_controls("portfolio", config)
        
        portfolio_profile = build_risk_profile(
            label="Portfolio",
            equity=bundle.history["total_value"],
            trades_df=bundle.trades,
            instrument_specs=instrument_specs,
            primary_confidence=config.var_confidence_primary,
            tail_confidence=config.var_confidence_tail,
            rolling_var_window_days=config.rolling_var_window_days,
            rolling_vol_windows=config.rolling_vol_windows,
            stress_multipliers=portfolio_stress,
            risk_free_rate=risk_free_rate,
        )
        
        with portfolio_top:
            _render_risk_profile_core(portfolio_profile, config)
        _render_stress_analysis(portfolio_profile, config)
        st.divider()
        st.markdown("#### Strategy Risk Drilldown")
        st.caption(
            "The table and charts below isolate one strategy slot at a time. "
            "Portfolio-only diversification effects are intentionally excluded."
        )

        strategy_profiles = _build_strategy_profiles(bundle, config, instrument_specs, risk_free_rate)
        _render_strategy_snapshot_table(strategy_profiles, config)

        strategy_names = sorted(strategy_profiles.keys())
        if not strategy_names:
            st.info("No strategy-level data available.")
            return

        selected_strategy = st.selectbox(
            "Strategy",
            strategy_names,
            key="risk_strategy_selector",
        )
        strategy_top = st.container()
        strategy_stress = _render_stress_controls("strategy", config)

        slot_lookup = {strategy_name: slot_id for slot_id, strategy_name in (bundle.slots or {}).items()}
        selected_slot_id = slot_lookup[selected_strategy]
        strategy_equity = build_strategy_equity_curve(
            bundle.history,
            slot_id=str(selected_slot_id),
            slot_weight=float(bundle.slot_weights.get(selected_slot_id)) if bundle.slot_weights and selected_slot_id in bundle.slot_weights else None,
            slot_count=len(bundle.slots or {}),
        )
        strategy_trades = (
            bundle.trades[bundle.trades["strategy"] == selected_strategy]
            if bundle.trades is not None and not bundle.trades.empty and "strategy" in bundle.trades.columns
            else pd.DataFrame()
        )
        strategy_profile = build_risk_profile(
            label=selected_strategy,
            equity=strategy_equity,
            trades_df=strategy_trades,
            instrument_specs=instrument_specs,
            primary_confidence=config.var_confidence_primary,
            tail_confidence=config.var_confidence_tail,
            rolling_var_window_days=config.rolling_var_window_days,
            rolling_vol_windows=config.rolling_vol_windows,
            stress_multipliers=strategy_stress,
            risk_free_rate=risk_free_rate,
        )
        with strategy_top:
            _render_risk_profile_core(strategy_profile, config)
        _render_stress_analysis(strategy_profile, config)
        return

    st.markdown("#### Strategy Risk")
    st.caption(
        "Single-asset mode analyses only the standalone strategy equity and daily PnL. "
        "No portfolio-only methods are applied here."
    )
    single_top = st.container()
    single_stress = _render_stress_controls("single", config)
    
    single_profile = build_risk_profile(
        label="Single Asset Strategy",
        equity=bundle.history["total_value"],
        trades_df=bundle.trades,
        instrument_specs=instrument_specs,
        primary_confidence=config.var_confidence_primary,
        tail_confidence=config.var_confidence_tail,
        rolling_var_window_days=config.rolling_var_window_days,
        rolling_vol_windows=config.rolling_vol_windows,
        stress_multipliers=single_stress,
        risk_free_rate=risk_free_rate,
    )
    with single_top:
        _render_risk_profile_core(single_profile, config)
    _render_stress_analysis(single_profile, config)

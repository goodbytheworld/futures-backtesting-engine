"""
Terminal UI settings models.

Separated from the main BacktestSettings module so runtime/dashboard concerns
do not get buried inside engine and execution configuration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TerminalUISettings(BaseModel):
    """
    Settings shared by the terminal analytics UI runtime.
    """

    rolling_sharpe_window_days: int = Field(
        default=90,
        description="Window in calendar days for rolling Sharpe calculation in the dashboard.",
    )
    dashboard_risk_rolling_var_window_days: int = Field(
        default=60,
        description="Trailing daily window for rolling VaR / ES curves in the dashboard risk tab.",
    )
    dashboard_risk_rolling_vol_window_short_days: int = Field(
        default=20,
        description="Short rolling volatility window in trading days for the dashboard risk tab.",
    )
    dashboard_risk_rolling_vol_window_medium_days: int = Field(
        default=50,
        description="Medium rolling volatility window in trading days for the dashboard risk tab.",
    )
    dashboard_risk_rolling_vol_window_long_days: int = Field(
        default=100,
        description="Long rolling volatility window in trading days for the dashboard risk tab.",
    )
    dashboard_risk_var_primary_confidence: float = Field(
        default=0.95,
        description="Primary historical VaR / ES confidence level for the dashboard risk tab.",
    )
    dashboard_risk_var_tail_confidence: float = Field(
        default=0.99,
        description="Tail historical VaR / ES confidence level for the dashboard risk tab.",
    )
    dashboard_bars_per_day: float = Field(
        default=13.0,
        description="Trading bars per calendar day for annualisation (13 = 30-min session 06:30-13:00).",
    )
    dashboard_stress_slider_min_multiplier: float = Field(
        default=1.0,
        description="Minimum multiplier exposed by stress-test sliders in the dashboard risk tab.",
    )
    dashboard_stress_slider_max_multiplier: float = Field(
        default=5.0,
        description="Maximum multiplier exposed by stress-test sliders in the dashboard risk tab.",
    )
    dashboard_stress_slider_step: float = Field(
        default=0.5,
        description="Step size for stress-test sliders in the dashboard risk tab.",
    )
    dashboard_stress_volatility_default_multiplier: float = Field(
        default=2.0,
        description="Default volatility shock multiplier for the dashboard risk tab.",
    )
    dashboard_stress_slippage_default_multiplier: float = Field(
        default=3.0,
        description="Default slippage shock multiplier for the dashboard risk tab.",
    )
    dashboard_stress_commission_default_multiplier: float = Field(
        default=2.0,
        description="Default commission shock multiplier for the dashboard risk tab.",
    )
    terminal_max_chart_points: int = Field(
        default=2000,
        description="Default maximum point budget for terminal chart payloads.",
    )
    terminal_trade_page_size: int = Field(
        default=25,
        description="Default page size for terminal trade-detail drilldowns.",
    )
    terminal_result_bundle_cache_ttl_seconds: float = Field(
        default=15.0,
        description="TTL in seconds for the small in-process result-bundle cache.",
    )
    terminal_min_correlation_samples: int = Field(
        default=5,
        description="Minimum resampled observations required before correlation views are rendered.",
    )
    terminal_correlation_cache_ttl_seconds: int = Field(
        default=600,
        description="TTL in seconds for expensive correlation-matrix payloads.",
    )
    terminal_risk_cache_ttl_seconds: int = Field(
        default=300,
        description="TTL in seconds for rolling stats and derived risk views.",
    )
    terminal_job_timeout_seconds: int = Field(
        default=1800,
        description="Timeout in seconds for queued terminal scenario jobs.",
    )
    terminal_job_max_retries: int = Field(
        default=2,
        description="Maximum retry count for queued terminal scenario jobs.",
    )
    terminal_sse_max_updates_per_second: float = Field(
        default=2.0,
        description="Maximum SSE update frequency for terminal job progress streams.",
    )
    terminal_worker_start_grace_seconds: float = Field(
        default=2.0,
        description="Grace period used before a newly spawned managed worker is treated as fully running.",
    )
    terminal_worker_stop_timeout_seconds: float = Field(
        default=2.0,
        description="Timeout in seconds when stopping the managed local worker process.",
    )
    terminal_benchmark_color: str = Field(
        default="#777777",
        description="Line color for benchmark overlays in terminal charts.",
    )
    terminal_strategy_colors: list[str] = Field(
        default_factory=lambda: ["#22C55E", "#3B82F6", "#EAB308", "#F97316", "#EC4899", "#A855F7"],
        description="Palette used for per-strategy chart series in portfolio mode.",
    )
    terminal_portfolio_total_color: str = Field(
        default="#FFFFFF",
        description="Primary color for the aggregate portfolio or strategy line.",
    )
    terminal_long_color: str = Field(
        default="#22C55E",
        description="Color used for long-side series in single-mode charts.",
    )
    terminal_short_color: str = Field(
        default="#EF4444",
        description="Color used for short-side series in single-mode charts.",
    )
    terminal_drawdown_color: str = Field(
        default="#EF4444",
        description="Color used for drawdown overlays and drawdown charts.",
    )
    terminal_rolling_sharpe_color: str = Field(
        default="#FFFFFF",
        description="Color used for rolling Sharpe mini-charts.",
    )
    terminal_rolling_vol_colors: list[str] = Field(
        default_factory=lambda: ["#22C55E", "#3B82F6", "#F59E0B"],
        description="Palette used for rolling-volatility series.",
    )
    terminal_stress_colors: list[str] = Field(
        default_factory=lambda: ["#22C55E", "#F59E0B", "#EF4444"],
        description="Palette used for stress-preview scenarios.",
    )
    terminal_var_colors: list[str] = Field(
        default_factory=lambda: ["#F59E0B", "#FBBF24", "#EF4444"],
        description="Palette used for VaR / ES risk overlays.",
    )
    terminal_loading_words: list[str] = Field(
        default_factory=lambda: [
            "Put red box into green.",
            "Oh, no! Claude, what you did!?",
            "Please, put red box into green one! Make no mistakes!",
            "It worked!",
            "Oh..., I forgot about the yellow one.",
        ],
        description="Rotating loading captions. And yes, you can change them... ;)",
    )
    terminal_loading_word_interval_ms: int = Field(
        default=1100,
        description="Interval in milliseconds for loading-word rotation.",
    )
    terminal_loading_eta_per_request_seconds: float = Field(
        default=2.2,
        description="Fallback ETA estimate (seconds) per pending chart request.",
    )

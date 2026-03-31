"""
Backtest engine configuration.

Engine-level settings only. Strategy-specific parameters are defined inside
each strategy class via get_search_space() and dataclass configs.
Loaded from environment variables (prefix: QUANT_BACKTEST_) or .env file.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .scenario import ScenarioEngineSettings
from .terminal_ui import TerminalUISettings


class BacktestSettings(BaseSettings):
    """
    Central configuration for the backtest engine runtime.

    Covers data, portfolio accounting, execution simulation, risk limits,
    IB Fetcher connectivity, batch orchestration, and walk-forward scheduling.
    Strategy-specific parameters must not be added here.
    """

    model_config = SettingsConfigDict(
        env_prefix="QUANT_BACKTEST_",
        env_file=".env",
        extra="allow",
    )

    # System paths
    base_dir: Path = Path(__file__).resolve().parents[3]
    cache_dir: Path = Field(default=Path("data/cache"), description="Parquet cache location")
    results_dir: Path = Field(default=Path("results"), description="Output directory for reports")
    batch_results_dir: Path = Field(
        default=Path("results/batch"),
        description="Output namespace reserved for lightweight batch analytics runs.",
    )
    wfo_batch_results_dir: Path = Field(
        default=Path("results/wfo_batch"),
        description="Output namespace reserved for walk-forward batch candidate exports.",
    )
    terminal_redis_url: Optional[str] = Field(
        default="redis://127.0.0.1:6379/0",
        description="Redis URL for terminal job queueing. Defaults to local Redis on port 6379.",
    )
    terminal_queue_name: str = Field(
        default="terminal-scenarios",
        description="RQ queue name for terminal-driven async scenario jobs.",
    )

    # Primary instrument
    default_symbol: str = "ES"

    # Bar settings
    low_interval: str = "30m"
    bar_type: str = "time"
    bar_size: float = 0.0

    # Portfolio and execution
    initial_capital: float = 1_000_000.0
    risk_free_rate: float = 0.02
    commission_rate: float = 2.5
    fixed_qty: int = 1
    portfolio_margin_ratio: float = 0.10

    # Deterministic spread model
    spread_mode: str = "adaptive_volatility"
    spread_ticks: int = 1
    spread_volatility_step_pct: float = 0.10
    spread_step_multiplier: float = 1.5
    spread_vol_lookback: int = 20
    spread_vol_baseline_lookback: int = 100
    spread_tick_multipliers_by_order_type: dict = Field(
        default_factory=dict,
        description=(
            "Optional per-order-type multipliers applied to spread ticks. "
            "Keys use MARKET/LIMIT/STOP/STOP_LIMIT."
        ),
    )
    commission_rate_by_order_type: dict = Field(
        default_factory=dict,
        description=(
            "Optional per-order-type commission overrides. "
            "Keys use MARKET/LIMIT/STOP/STOP_LIMIT."
        ),
    )
    intrabar_conflict_resolution: str = Field(
        default="pessimistic",
        description=(
            "Conflict policy when a coarse bar proves multiple mutually exclusive "
            "execution paths. Supported values: pessimistic, lower_timeframe."
        ),
    )
    intrabar_resolution_timeframe: Optional[str] = Field(
        default=None,
        description=(
            "Optional lower timeframe used only when intrabar_conflict_resolution "
            "is set to lower_timeframe. Missing or incomplete lower-TF data "
            "must fall back to pessimistic resolution."
        ),
    )

    # Trading hours
    use_trading_hours: bool = True
    trade_start_time: Optional[str] = "06:00"
    trade_end_time: Optional[str] = "15:00"
    eod_close_time: Optional[str] = "15:30"

    # Risk limits
    max_daily_loss: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_account_floor: Optional[float] = None

    # Statistical filters / numerical protections
    hl_lambda_min: Optional[float] = 1e-4
    hl_max_cap: Optional[float] = 500.0

    # Volatility regime analytics defaults
    vol_regime_window_default: int = 50
    vol_history_window_default: int = 500
    vol_min_pct_default: float = 0.20
    vol_max_pct_default: float = 0.80

    # Batch plot defaults
    batch_plot_min_pnl_pct: float = -80.0
    batch_plot_max_drawdown_pct: float = 80.0
    batch_plot_max_table_rows: int = 20

    # IB Fetcher
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 1
    ib_timeout: int = 30
    max_historical_years: int = 2
    delayed_data_minutes: int = 15
    ib_use_rth: bool = False

    # Cache management
    max_cache_staleness_days: int = Field(
        default=10,
        description="Maximum allowed cache age in days for backtest runs.",
    )

    def get_ib_request_delay(self) -> float:
        """Standard pacing delay to respect IB rate limits (~6 req/min)."""
        return 11.0

    # Terminal / analytics UI settings
    terminal_ui: "TerminalUISettings" = Field(default_factory=lambda: TerminalUISettings())
    scenario_engine: "ScenarioEngineSettings" = Field(
        default_factory=lambda: ScenarioEngineSettings()
    )

    @property
    def dashboard(self) -> "TerminalUISettings":
        """Legacy alias kept while older analytics modules finish migrating."""
        return self.terminal_ui

    # Walk-forward validation scheduling
    wfo_n_folds: int = 5
    wfo_test_size_pct: float = 0.10
    wfo_n_trials: int = 120
    wfo_max_parameters: int = 6

    # Pruning / quality gates
    wfo_prune_min_trades: int = 7
    wfo_prune_max_dd_pct: float = 35.0
    wfo_prune_target_trades_mult: int = 2

    # Robustness / consistency gates
    wfo_pass_min_profitable_folds: int = 3
    wfo_warn_min_profitable_folds: int = 2
    wfo_pass_min_consecutive_profitable_folds: int = 2
    wfo_warn_min_consecutive_profitable_folds: int = 1
    wfo_min_sharpe_per_fold: float = 0.3

    # Lightweight batch orchestration
    batch_max_workers: int = Field(
        default=4,
        description="Default worker count for batch and WFO-batch orchestration.",
    )
    batch_progress_bar_width: int = Field(
        default=32,
        description="Character width used by CLI batch progress bars.",
    )
    batch_plot_figure_width: float = Field(
        default=16.0,
        description="Default Matplotlib figure width for lightweight batch analytics plots.",
    )
    batch_plot_figure_height: float = Field(
        default=9.0,
        description="Default Matplotlib figure height for lightweight batch analytics plots.",
    )
    batch_equity_floor_pct: float = Field(
        default=-100.0,
        description="Lower bound for displayed batch PnL and drawdown percentages.",
    )
    batch_plot_ruin_equity_ratio: float = Field(
        default=0.01,
        description=(
            "Positive log-chart surrogate used once batch equity reaches or "
            "falls below the configured floor."
        ),
    )

    # Path helpers
    def get_results_path(self) -> Path:
        """Create and return the results directory path."""
        path = self.base_dir / self.results_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_batch_results_path(self) -> Path:
        """Create and return the lightweight batch results directory."""
        path = self.base_dir / self.batch_results_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_wfo_batch_results_path(self) -> Path:
        """Create and return the WFO batch results directory."""
        path = self.base_dir / self.wfo_batch_results_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_cache_path(self) -> Path:
        """Create and return the data cache directory path."""
        path = self.base_dir / self.cache_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Instrument specifications
    instrument_specs: dict = Field(
        default_factory=lambda: {
            "ES": {"tick_size": 0.25, "multiplier": 50.0},
            "NQ": {"tick_size": 0.25, "multiplier": 20.0},
            "CL": {"tick_size": 0.01, "multiplier": 1000.0},
            "GC": {"tick_size": 0.10, "multiplier": 100.0},
            "SI": {"tick_size": 0.005, "multiplier": 5000.0},
            "NG": {"tick_size": 0.001, "multiplier": 10000.0},
            "PL": {"tick_size": 0.10, "multiplier": 50.0},
            "YM": {"tick_size": 1.0, "multiplier": 5.0},
            "RTY": {"tick_size": 0.10, "multiplier": 50.0},
            "ZC": {"tick_size": 0.25, "multiplier": 50.0},
            "ZB": {"tick_size": 0.03125, "multiplier": 1000.0},
            "6E": {"tick_size": 0.00005, "multiplier": 125000.0},
        },
        description="Per-instrument tick sizes and dollar multipliers.",
    )

    def get_instrument_spec(self, symbol: str) -> dict:
        """
        Return tick size, multiplier, and margin ratio for a symbol.

        Falls back to generic defaults if the symbol is unknown, allowing the
        engine to run on unlisted instruments without crashing.
        """

        spec = dict(self.instrument_specs.get(symbol, {"tick_size": 0.01, "multiplier": 1.0}))
        spec.setdefault("margin_ratio", float(self.portfolio_margin_ratio))
        return spec


__all__ = ["BacktestSettings"]

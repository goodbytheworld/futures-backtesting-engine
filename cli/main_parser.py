"""
Primary parser construction for ``run.py``.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest_engine.settings import BacktestSettings


CLI_EPILOG = """
Detailed examples and workflow notes live in USAGE.md.

Quick start:
  python run.py --download ES NQ YM RTY CL NG GC SI 6E
  python run.py --backtest --strategy sma_pullback --symbol ES --tf 1h
  python run.py --wfo --strategy three_bar_mr --symbol YM --tf 1h
  python run.py --portfolio-backtest --dashboard
  python run.py batch --strategies sma_pullback ict_ob --symbol ES --tf 1h 30m
"""


def build_main_parser(strategy_list: str) -> argparse.ArgumentParser:
    """
    Builds the main repository CLI parser.

    Args:
        strategy_list: Human-readable list of strategy IDs and aliases.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Backtesting Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    parser.add_argument("--download", nargs="+", help="Download data for symbols via IB")
    parser.add_argument(
        "--validate-data",
        nargs="*",
        metavar="SYMBOL",
        help=(
            "Validate cached OHLCV data quality. "
            "Without SYMBOL validates the full cache; "
            "with SYMBOL validates only that instrument."
        ),
    )
    parser.add_argument("--backtest", action="store_true", help="Run single-asset backtest")
    parser.add_argument("--wfo", action="store_true", help="Run Walk-Forward Optimization")
    parser.add_argument(
        "--strategy",
        type=str,
        default="sma_pullback",
        help=f"Strategy name ({strategy_list})",
    )
    parser.add_argument(
        "--symbol",
        dest="symbol_override",
        type=str,
        default=None,
        help="Override default symbol for --backtest or --wfo",
    )
    parser.add_argument(
        "--tf",
        dest="timeframes",
        nargs="+",
        default=None,
        metavar="TIMEFRAME",
        help="Override timeframe for --backtest or --wfo",
    )
    parser.add_argument(
        "--portfolio-backtest",
        action="store_true",
        help="Run multi-strategy portfolio backtest",
    )
    parser.add_argument(
        "--portfolio-config",
        type=str,
        default="src/backtest_engine/portfolio_layer/portfolio_config_example.yaml",
        help="Path to YAML portfolio config",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help=(
            "Launch terminal dashboard. "
            "When combined with --backtest/--portfolio-backtest, "
            "opens after the run completes."
        ),
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=None,
        metavar="PORT",
        help=(
            "HTTP port for the terminal dashboard (default: 8000 or "
            "TERMINAL_DASHBOARD_PORT). If busy, the next free port is used."
        ),
    )
    parser.add_argument("--results-subdir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--scenario-id", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--baseline-run-id", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--scenario-type", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--scenario-params-json", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("symbol_positional", nargs="?", default=None, help=argparse.SUPPRESS)
    return parser


def apply_single_mode_overrides(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    settings: "BacktestSettings",
) -> "BacktestSettings":
    """
    Applies single-run symbol and timeframe overrides to shared settings.

    Args:
        parser: Parser used for validation failures.
        args: Parsed CLI namespace.
        settings: Base runtime settings.

    Returns:
        Updated settings instance.
    """
    updates: dict[str, object] = {}
    flag_symbol = str(args.symbol_override).strip() if args.symbol_override else ""
    positional_symbol = (
        str(args.symbol_positional).strip() if args.symbol_positional else ""
    )

    if (
        flag_symbol
        and positional_symbol
        and flag_symbol.upper() != positional_symbol.upper()
    ):
        parser.error("Use either '--symbol ES' or positional 'ES', not both.")

    resolved_symbol = flag_symbol or positional_symbol
    if resolved_symbol:
        updates["default_symbol"] = resolved_symbol.upper()

    timeframes = list(args.timeframes or [])
    if timeframes:
        if len(timeframes) != 1:
            parser.error(
                "--tf accepts exactly one value for --backtest and --wfo. "
                "Use 'batch' or 'wfo-batch' for multi-timeframe sweeps."
            )
        updates["low_interval"] = str(timeframes[0]).strip()

    return settings.model_copy(update=updates) if updates else settings

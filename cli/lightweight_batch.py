"""
Helpers for the positional ``batch`` and ``wfo-batch`` CLI modes.
"""

from __future__ import annotations

import argparse
from typing import Sequence


LIGHTWEIGHT_BATCH_COMMANDS = {"batch", "wfo-batch"}


def build_lightweight_batch_parser(command_name: str) -> argparse.ArgumentParser:
    """
    Builds the dedicated parser for positional batch commands.

    Args:
        command_name: ``batch`` or ``wfo-batch``.

    Returns:
        Configured argument parser for that command.
    """
    parser = argparse.ArgumentParser(
        prog=f"python run.py {command_name}",
        description=(
            "Lightweight multi-scenario batch backtester."
            if command_name == "batch"
            else "Lightweight multi-scenario WFO batch runner."
        ),
    )
    strategy_group = parser.add_mutually_exclusive_group(required=True)
    strategy_group.add_argument("--strategy", type=str, help="One strategy ID or alias")
    strategy_group.add_argument(
        "--strategies",
        nargs="+",
        help="One or many strategy IDs or aliases",
    )
    symbol_group = parser.add_mutually_exclusive_group(required=True)
    symbol_group.add_argument(
        "--symbol",
        dest="symbols",
        nargs="+",
        help="One or many futures symbols",
    )
    symbol_group.add_argument(
        "--symbols",
        dest="symbols",
        nargs="+",
        help="One or many futures symbols",
    )
    parser.add_argument(
        "--tf",
        nargs="+",
        required=True,
        metavar="TIMEFRAME",
        help="One or many timeframes (for example: 1h 30m 5m 1m)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Optional worker override for the batch process pool",
    )
    return parser


def dispatch_lightweight_batch_command(argv: Sequence[str]) -> bool:
    """
    Dispatches positional batch commands before legacy parser handling.

    Args:
        argv: Raw CLI arguments excluding the executable name.

    Returns:
        ``True`` when a lightweight command was handled.
    """
    if not argv:
        return False

    command_name = str(argv[0]).strip().lower()
    if command_name not in LIGHTWEIGHT_BATCH_COMMANDS:
        return False

    parser = build_lightweight_batch_parser(command_name)
    args = parser.parse_args(list(argv[1:]))

    from src.backtest_engine.config import BacktestSettings

    settings = BacktestSettings()
    strategy_names = [args.strategy] if args.strategy else list(args.strategies or [])

    if command_name == "batch":
        from cli.batch import run as run_batch

        run_batch(
            strategy_names=strategy_names,
            symbols=args.symbols,
            timeframes=args.tf,
            settings=settings,
            max_workers=args.workers,
        )
    else:
        from cli.wfo_batch import run as run_wfo_batch

        run_wfo_batch(
            strategy_names=strategy_names,
            symbols=args.symbols,
            timeframes=args.tf,
            settings=settings,
            max_workers=args.workers,
        )
    return True

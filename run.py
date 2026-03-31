"""Repository CLI entry point."""

from __future__ import annotations

import sys

from cli.data_validation import run_data_validation
from cli.lightweight_batch import dispatch_lightweight_batch_command
from cli.main_parser import apply_single_mode_overrides, build_main_parser
from cli.runtime_dashboard import launch_dashboard


def main(argv: list[str] | None = None) -> int:
    """
    Runs the repository CLI.

    Methodology:
        ``run.py`` stays intentionally thin. Argument construction, dashboard
        runtime helpers, lightweight batch parsing, and validation routines all
        live in adjacent modules so the entry point remains a small orchestration
        shell instead of another monolith.

    Args:
        argv: Optional CLI args excluding the executable name.

    Returns:
        Process exit code.
    """
    cli_args = list(sys.argv[1:] if argv is None else argv)
    if dispatch_lightweight_batch_command(cli_args):
        return 0

    from src.strategies.registry import get_strategy_ids

    strategy_list = ", ".join(get_strategy_ids(include_aliases=True))
    parser = build_main_parser(strategy_list)
    args = parser.parse_args(cli_args)

    if not cli_args:
        parser.print_help()
        return 1

    if (
        args.dashboard
        and not args.backtest
        and not args.portfolio_backtest
        and not args.wfo
    ):
        launch_dashboard(dashboard_port=args.dashboard_port)
        return 0

    from src.backtest_engine.config import BacktestSettings

    settings = apply_single_mode_overrides(parser, args, BacktestSettings())

    if args.download:
        from src.data import IBFetcher

        print("=" * 60)
        print(f"  Downloading data: {args.download}")
        print("=" * 60)
        fetcher = IBFetcher(settings=settings)
        for symbol in args.download:
            fetcher.fetch_all_timeframes(symbol)
        print("Download complete.")

    if args.validate_data is not None:
        run_data_validation(
            settings=settings,
            symbols=args.validate_data,
            timeframes=args.timeframes,
        )

    if args.backtest:
        from cli.single import run as run_backtest

        run_backtest(args.strategy, settings)
        if args.dashboard:
            launch_dashboard(dashboard_port=args.dashboard_port)

    if args.wfo:
        from cli.wfo import run as run_wfo

        run_wfo(args.strategy, settings)

    if args.portfolio_backtest:
        from cli.portfolio import run as run_portfolio

        run_portfolio(
            args.portfolio_config,
            results_subdir=args.results_subdir,
            scenario_id=args.scenario_id,
            baseline_run_id=args.baseline_run_id,
            scenario_type=args.scenario_type,
            scenario_params_json=args.scenario_params_json,
        )
        if args.dashboard:
            launch_dashboard(dashboard_port=args.dashboard_port)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# TODO

- [ ] **PnL Decay (Forward Horizon) showing zero**: Investigate and fix the calculation inside `exit_analysis.py`.
- [ ] **Portfolio Allocator Sizing Bug**: Correct the contract sizing logic in `allocator.py` to use instrument `multiplier` instead of `tick_size`.
- [ ] **Stat Level Strategy Refinement**: Review logic for signal generation in high-vol regimes.
- [ ] **Dashboard Performance**: Optimize Parquet loading for very large backtests (>100k trades).

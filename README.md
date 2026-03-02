# Single Asset Backtester

A high-performance event-driven backtesting engine with Walk-Forward Optimization.

**Pros:** Fast vectorized O(1) execution, robust Optuna WFO framework, strict clean code principles.
**Cons:** Single instrument limitation per run, lacks portfolio-level risk management.
**Solutions:** Prevents look-ahead bias by shifting signals. Caches historical data in Parquet format for maximum loading speed.
**Architecture:** Abstract engine running decoupled strategy implementations over pandas DataFrames. 

Demo strategies currently included: SMA Crossover and Mean Reversion.

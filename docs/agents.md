# Project Setup & Context for AI Agents (LLMs)

**Objective Name:** Quant Backtesting Engine
**Audience:** Artificial Intelligence Agents (LLMs) contributing to or maintaining the codebase.
**Status:** MANDATORY READING BEFORE MODIFYING CODE.

---

## 1. Project Purpose
This is a Python-based, Institutional-Grade backtesting platform. It supports:
1.  **Single-Asset Backtesting**: Individual strategy runs on single instruments.
2.  **Walk-Forward Optimization (WFO)**: Systematic parameter robustness testing.
3.  **Multi-Strategy Portfolio Backtesting**: Running multiple strategies concurrently with shared capital, dynamic allocation, and risk management.
4.  **Analytics & Visualization**: A Streamlit dashboard (`src/backtest_engine/analytics/dashboard/app.py`) for PnL and risk analysis.

---

## 2. Core Architecture & Modules

The entry point is **`run.py`** at the project root. It purely parses arguments and dispatches to handlers in `cli/`.

*   **`cli/`**: CLI handlers (`single.py`, `wfo.py`, `portfolio.py`).
*   **`src/backtest_engine/`**: The core execution engine.
    *   `settings.py`: `BacktestSettings` (pydantic-settings, `.env` file driven). **All magic numbers go here.**
    *   `engine.py` & `execution.py`: Single-asset engine and order handling.
    *   `portfolio_layer/`: Multi-asset engine.
        *   `domain/`: Pure data structures (`PortfolioConfig`, `StrategySlot`, `TargetPosition`).
        *   `allocation/`: Capital sizing (`Allocator`).
        *   `scheduling/`: Rebalance gating (Intrabar, Daily).
        *   `execution/`: Fills and ledger (`PortfolioBook`, `StrategyRunner`).
        *   `engine/`: `PortfolioBacktestEngine` containing the main event loop.
        *   `reporting/`: Result serialization (Parquet, JSON).
    *   `analytics/`: Post-execution dashboard (Streamlit) and metrics.
*   **`src/strategies/`**: Trading logic.
    *   All strategies inherit from `BaseStrategy` (`base.py`).
    *   **Registry**: `registry.py` is the central mapping for CLI/YAML IDs (e.g., `"zscore"`) to class paths.
*   **`data/`**: Data ingestion (`DataLake` -> OHLCV DataFrames, IB Fetcher).

---

## 3. Critical System Invariants

1.  **No-Lookahead Guarantee**: A signal is generated at `close[t]`. The resulting order is queued and MUST fill at `open[t+1]`.
2.  **Shared-Capital Equation**: `total_equity == cash + Σ(qty × last_known_price × multiplier)`.
3.  **Settings Layering**: `.env` variables override defaults -> `BacktestSettings` reads them -> `portfolio_config.yaml` can override them per-run.

---

## 4. Coding Standards (CLEAN CODE MCP)

As an AI modifying this codebase, you **MUST** strictly adhere to these rules:

### A. Language & Tone
*   **ENGLISH ONLY**. No Cyrillic or other languages in comments, variables, or docs.

### B. Type Safety
*   All function signatures MUST have explicit type hints (`from typing import List, Dict, Optional`, etc.).
*   Use `pydantic` or `dataclasses` for complex data structures instead of raw dictionaries where possible.

### C. No Magic Numbers
*   **NEVER hardcode parameters** (windows, thresholds, rates) in logic files.
*   Extract them to `src/backtest_engine/settings.py` so they can be injected/configured.

### D. Resilient Error Handling
*   **For Backtests**: Log non-critical failures and continue. Do not crash the entire backtest over one bad bar if possible.
*   **For Live/Critical**: Use circuit breakers (e.g., if a model fails to fit 5 times, stop trading).

### E. Documentation (Google Style)
Every class and public method must have a docstring explaining **Why (Methodology)**, not just *What*.

**Template Example**:
```python
def calculate_target(self, signal: StrategySignal, equity: float) -> TargetPosition:
    """
    Computes to the target position size for a strategy signal.
    
    Methodology:
    Uses standard volatility targeting based on risk parity. The target
    notional is scaled by the inverse of the asset's recent volatility.
    
    Args:
        signal: Generated signal containing direction and conviction.
        equity: Current total portfolio equity allocated to this slot.
        
    Returns:
        TargetPosition object with the desired contract quantity.
    """
```

### F. Analytics & Dashboard Rule
*   `src/backtest_engine/analytics/dashboard/core/transforms.py` is the **Pure computation layer**. It should have NO Streamlit imports (`st.something`), no I/O, and no side-effects. This allows it to be easily unit-tested.
*   `app.py` handles Streamlit layout. `components.py` handles Streamlit widgets and DataFrames. `charts.py` handles Plotly figures.

---

## 5. Development Workflow

1.  **Add a Strategy**: Implement in `src/strategies/`, then register in `src/strategies/registry.py`.
2.  **Add a Metric**: Compute in `transforms.py`, visualize in `charts.py`, render in `app.py`.
3.  **Run Tests**: Ensure unit, integration, and regression tests pass when touching `portfolio_layer` or `engine.py`.

"""
tests/unit/test_strategies.py

Parametric contract tests for all registered strategies.
"""
from typing import Dict, Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.strategies.registry import get_strategy_ids, load_strategy_by_id


class MockSettings:
    """Canonical minimal fake settings."""
    def __init__(self) -> None:
        self.default_symbol = "BTCUSDT"
        self.fixed_qty = 0.1
        self.low_interval = "1m"
        self.max_cache_staleness_days = 7
        
    def get_instrument_spec(self, symbol: str) -> Dict[str, Any]:
        return {
            "tick_size": 0.25,
            "min_price_increment": 0.25,
            "price_precision": 2,
            "qty_step": 1.0,
            "qty_precision": 0,
        }


class MockPortfolio:
    """Canonical minimal fake portfolio."""
    def __init__(self) -> None:
        self.positions: Dict[str, float] = {"BTCUSDT": 0.0}


class MockEngine:
    """Canonical minimal fake engine."""
    def __init__(self) -> None:
        self.settings = MockSettings()
        self.portfolio = MockPortfolio()
        
        # Strategies typically expect engine.data to be a dictionary or DataFrame
        # with at least open, high, low, close, volume pandas Series.
        idx = pd.date_range("2020-01-01", periods=100, freq="1min")
        self.data = {
            "open": pd.Series(100.0, index=idx),
            "high": pd.Series(105.0, index=idx),
            "low": pd.Series(95.0, index=idx),
            "close": pd.Series(102.0, index=idx),
            "volume": pd.Series(1000.0, index=idx),
        }


@pytest.mark.parametrize("strategy_id", get_strategy_ids())
def test_strategy_contract(strategy_id: str) -> None:
    """
    Ensures that every registered strategy satisfies the BaseStrategy contract:
    - Can be instantiated with a canonical minimal fake engine.
    - Exposes a callable on_bar(bar) method.
    - Can return its search space without error.
    """
    strategy_class = load_strategy_by_id(strategy_id)
    engine = MockEngine()
    
    # 1. Instantiation contract
    strategy = strategy_class(engine=engine)
    
    # 2. Callable on_bar method contract
    assert hasattr(strategy, "on_bar"), f"Strategy {strategy_id} missing on_bar"
    assert callable(strategy.on_bar), f"Strategy {strategy_id} on_bar is not callable"
    
    # Execute a loose test on on_bar just to ensure it's not fundamentally broken when given typical data.
    # While some indicators may be uninitialized, the contract dictates a List[Order] return.
    dummy_bar = pd.Series({
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0,
    })
    dummy_bar.name = pd.Timestamp("2020-01-01 00:00:00")
    
    try:
        result = strategy.on_bar(dummy_bar)
        assert isinstance(result, list), f"Strategy {strategy_id} on_bar must return a list"
    except Exception as e:
        pytest.fail(f"Strategy {strategy_id} failed on dummy on_bar call with minimal canonical engine data: {e}")
        
    # 3. Search space contract
    space = strategy_class.get_search_space()
    assert isinstance(space, dict), f"Strategy {strategy_id} get_search_space() must return a dict"

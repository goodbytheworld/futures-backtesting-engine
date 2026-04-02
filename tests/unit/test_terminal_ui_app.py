from __future__ import annotations

from pathlib import Path

import src.backtest_engine.runtime.terminal_ui.app as terminal_app


def test_static_asset_version_changes_when_renderer_module_changes(tmp_path: Path, monkeypatch) -> None:
    """Cache-busting must include split chart renderer modules, not only legacy entrypoints."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    for relative_path in (
        "terminal.css",
        "terminal.js",
        "charts.js",
        "operations.js",
        "charts_renderers_core.js",
        "terminal_tokens.css",
    ):
        path = static_dir / relative_path
        path.write_text("initial", encoding="utf-8")

    monkeypatch.setattr(terminal_app, "_STATIC_DIR", static_dir)

    version_before = terminal_app._build_static_asset_version()

    (static_dir / "charts_renderers_core.js").write_text("updated renderer body", encoding="utf-8")
    version_after_renderer_change = terminal_app._build_static_asset_version()

    assert version_after_renderer_change != version_before


def test_static_asset_version_changes_when_imported_css_module_changes(tmp_path: Path, monkeypatch) -> None:
    """Cache-busting must include imported terminal CSS modules, not only terminal.css."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    for relative_path in (
        "terminal.css",
        "terminal.js",
        "charts.js",
        "operations.js",
        "terminal_layout.css",
    ):
        path = static_dir / relative_path
        path.write_text("initial", encoding="utf-8")

    monkeypatch.setattr(terminal_app, "_STATIC_DIR", static_dir)

    version_before = terminal_app._build_static_asset_version()

    (static_dir / "terminal_layout.css").write_text("updated layout rules", encoding="utf-8")
    version_after_css_change = terminal_app._build_static_asset_version()

    assert version_after_css_change != version_before

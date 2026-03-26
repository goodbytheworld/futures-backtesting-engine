---
name: Analytics Roadmap
overview: Split the remaining analytics work into small implementation plans, plus a parallel repository hygiene track (full architectural cleanup) so feature delivery and decoupling do not block each other indefinitely.
todos:
  - id: plan-0-repo-hygiene
    content: "Run the full-repository hygiene epics: terminal UI placement, CLI facade, strategy purity, fast_bar audit, data_layer alignment, test fixtures — in small mergeable slices validated against this repo."
    status: pending
  - id: plan-a-scenario-foundation
    content: Prepare the first implementation plan for real stress-testing foundations, scenario contracts, and queue job taxonomy.
    status: pending
  - id: plan-b-stress-ui
    content: Prepare the second implementation plan for the Stress Testing tab and stacked multi-job progress loaders in terminal_ui.
    status: pending
  - id: plan-c-simulation-bankruptcy
    content: Prepare the third implementation plan for Monte Carlo, bootstrapping, regime-switching simulations, and bankruptcy estimation artifacts.
    status: pending
  - id: plan-d-extract-shared
    content: Prepare a migration plan to extract shared analytics modules out of analytics/dashboard before deletion.
    status: pending
  - id: plan-e-docs-cleanup
    content: Prepare a final cleanup plan for deleting Streamlit UI and updating README/docs/contributor documentation.
    status: pending
isProject: false
---

# Analytics UI Roadmap

## Starting with “project hygiene” — agreed approach

**Opinion:** Beginning with порядок в репозитории — разумно, если это **серия коротких, проверяемых срезов**, а не один большой PR на месяц. Внешний архитектурный обзор полезен как чеклист, но **каждый пункт нужно подтвердить по фактическому коду** (обзор мог не иметь полного контекста).

**Выбранный объём (user):** полный трек из обзора — вынесение UI, CLI facade, «чистые» стратегии, аудит `fast_bar`, выравнивание доступа к данным, улучшение тестовой оснастки — как **отдельные эпики**, параллельно или чередуясь с Plan A–E так, чтобы аналитика **не зависела** от завершения всего списка.

**Пересечение с этим roadmap:** пункты про `analytics/dashboard` и `terminal_ui` совпадают с **Plan D** и частично облегчают **Plan B** (графики сценариев, меньше импортов из Streamlit-дерева). Остальное (CLI, strategies, bar pipeline) — **сквозная инфраструктура**, не только analytics.

## Plan 0 — Repository hygiene (full review track)

Выполнять **порциями**; после каждой порции — прогон тестов и фиксация «границы ответственности» в одном коротком документе или комментарии в PR.

1. **Terminal UI как отдельный concern** — вынести сервер из глубокой вложенности под `analytics/` в верхнеуровневый пакет (например `server/` или `ui/`), сохранив чёткий импорт из `backtest_engine` без циклов. Worker lifecycle (`worker_manager`, platform helpers) либо рядом, либо с отдельной точкой входа для автономного воркера.
2. **CLI → тонкий facade** — `cli/`* вызывает что-то вроде `BacktestService.run(...)`, а не внутренности движка напрямую; интеграционные тесты позже бьют по тому же пути.
3. **Стратегии ближе к чистым функциям** — целевой контракт `(bars, params) → сигналы` без импорта движка внутри стратегии; стратегии-специфичные unit-тесты по мере миграции.
4. **Один источник правды для данных** — развести `dashboard/core/data_layer` и путь движка (`data_lake` и т.д.): общий адаптер/репозиторий, чтобы UI и worker не жили на параллельных чтениях Parquet с расхождением семантики.
5. **Аудит `fast_bar` vs медленный путь** — зафиксировать, что используется в прод-пути; легаси пометить или удалить, чтобы не было двух «истин» для баров.
6. **Тестируемость UI** — там, где маршруты напрямую бьют в файловую систему, ввести инжектируемый слой (репозиторий/порт); расширить `conftest` по подпакетам при росте фикстур.
7. **Optuna / SQLite** — зафиксировать как риск при параллельных прогонах; отложенная опция: PostgreSQL или абстракция хранилища исследований (не блокер для analytics roadmap, но в списке техдолга).

**Явно не делать:** останавливать Plan A до «идеальной» архитектуры — порядок и фичи идут **чередой** (например: срез 0.1 data_layer + границы импортов → Plan A контракт → следующий срез UI package).

## Recommended Order (analytics track)

1. **Plan A — Real stress-testing foundation**

Define what a stress scenario is, how it mutates baseline inputs, how it mutates the execution model, what artifacts it writes, and how job types are represented in the queue.

1. **Plan B — Stress Testing tab + worker UX**

Add a dedicated `Stress Testing` tab beside `Risk`, wire it to the scenario engine, and replace the current single active-job view with a stack of concurrent progress loaders.

1. **Plan C — Simulation engine + bankruptcy estimation**

Add Monte Carlo, bootstrapping, regime-switching simulations, and `probability_of_bankruptcy` outputs only after the simulation artifact contract exists.

1. **Plan D — Shared analytics extraction from legacy dashboard**

Move framework-neutral loaders, transforms, scenario helpers, and risk models out of `analytics/dashboard/` into a neutral package so `terminal_ui` no longer depends on the Streamlit tree.

1. **Plan E — Delete Streamlit UI + open-source docs cleanup**

Remove the Streamlit-only files only after Plan D lands, then update all docs, add `contributor_readme.md`, and clean the repository structure for GitHub.

## Stress Testing Definition

For this roadmap, a real stress test is **not** a simple multiplier rerun.

A real stress test must rerun the strategy under changed market and execution conditions:

- different volatility regimes using clustered/regime-aware changes, not only scaling,
- degraded liquidity with worse fills and partial fills,
- latency and execution delay,
- spread widening,
- regime shifts such as trend to chop or low volatility to high volatility,
- tail events such as gaps, crash-like sequences, or forced adverse windows.

This means the implementation must support **both**:

- mutated or resampled market inputs,
- mutated execution behavior.

## Scenario Families To Support

The dedicated `Stress Testing` tab should be the home for these scenario families:

- Volatility regime shift
- Liquidity shock
- Slippage model with state-dependent behavior, not a flat multiplier
- Market replay over the harshest available historical windows in local data
- Monte Carlo / bootstrapping
- Regime-switching simulations

Because the local dataset does not currently guarantee 2008 or 2020 coverage, the replay feature should initially select the harshest available windows from the accessible data using volatility, drawdown, gap behavior, and abnormal volume heuristics.

## Why This Order

- The current queue and progress plumbing already exists in [src/backtest_engine/runtime/terminal_ui/jobs.py](c:/FuckingpyhonPartNumberZERO/Backtests/Backtesting%20ground/simple%20strategys/src/backtest_engine/runtime/terminal_ui/jobs.py) and [src/backtest_engine/runtime/terminal_ui/routes_operations.py](c:/FuckingpyhonPartNumberZERO/Backtests/Backtesting%20ground/simple%20strategys/src/backtest_engine/runtime/terminal_ui/routes_operations.py), but it currently models only a simple `stress_rerun` with basic multiplier payloads.
- The current `Risk` tab in [src/backtest_engine/runtime/terminal_ui/templates/partials/panel_risk.html](c:/FuckingpyhonPartNumberZERO/Backtests/Backtesting%20ground/simple%20strategys/src/backtest_engine/runtime/terminal_ui/templates/partials/panel_risk.html) is still a preview/approximation surface, so it should remain lightweight while heavier scenario execution moves into a separate tab.
- The current terminal shell can host a new tab via [src/backtest_engine/runtime/terminal_ui/constants.py](c:/FuckingpyhonPartNumberZERO/Backtests/Backtesting%20ground/simple%20strategys/src/backtest_engine/runtime/terminal_ui/constants.py), but the backend model has to be widened before that tab can honestly represent “real stress testing.”
- Deleting `analytics/dashboard/` now would still break `terminal_ui`, because shared loaders and transforms are still imported from that package.

## Plan A Scope Boundaries

**Include:**

- Define a scenario contract that distinguishes market-data shocks from execution-model shocks.
- Introduce scenario families and job taxonomy for deterministic reruns versus simulation jobs.
- Define the artifact layout for stress scenario outputs and for future `simulation_analysis` outputs.
- Define worker progress stages that are richer than the current coarse `3`-step scenario job.
- Choose the minimum backend policy: keep `Redis/RQ` as the execution backend and add a thin launcher/bootstrap, not a second queue system.
- Identify which current code can stay as preview-only under `Risk` and which code must migrate into the dedicated stress engine path.

**Do not include yet:**

- Full terminal UI implementation of all scenario families.
- Deleting Streamlit files.
- Large naming migrations for public flags or settings.

## Plan B Scope Boundaries

**Include:**

- Add `stress-testing` as a separate bottom tab beside `risk`.
- Build a scenario launcher surface with explicit scenario family selection.
- Show multiple live loaders at once, not one selected active job.
- Reuse SSE and durable job metadata, but generalize them from a single scenario rerun to multiple job types.
- Add the smallest acceptable worker UX: documented launcher, queue health, and worker availability.

## Plan C Scope Boundaries

**Include:**

- Monte Carlo and bootstrapping path generation.
- Regime-switching simulations.
- Bankruptcy probability metrics and persistence.
- Reproducibility metadata such as seeds, sampling policy, and simulation parameters.

## Recommended Backend Decision

Use the existing `Redis/RQ` queue as the primary execution backend for the first phases, and add only a thin bootstrap layer for developers and users.

Reasoning:

- `jobs.py` already provides durable metadata, retries, and SSE progress.
- A local in-process queue would duplicate logic before the stress engine contract is even stable.
- The current need is a cleaner worker entrypoint and better UX, not a second execution backend.

## Phase Risks To Watch

- If Plan A is skipped, the new tab will inherit the current multiplier-only scenario model and will not meet the definition of real stress testing.
- The current queue metadata assumes one scenario shape and coarse progress stages; that is too narrow for market replay and simulation jobs.
- `analytics/dashboard/` currently mixes legacy UI and shared logic, so migration and deletion must stay after feature delivery.


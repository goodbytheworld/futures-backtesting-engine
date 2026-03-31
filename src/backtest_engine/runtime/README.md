# Runtime Package

Runtime-facing delivery surfaces live here.

## Current Surface

- `terminal_ui/` is the active FastAPI analytics runtime for saved artifacts.

## Design Rule

Keep runtime packages focused on HTTP, rendering, and runtime composition. Shared analytics, artifact loading, and execution logic should stay in `analytics/`, `services/`, and engine packages rather than drifting into the runtime layer.

# Dockit Backend – Runtime Map (single source of truth)

## Active runtime (in use)

### Free-text quote preview (Lovable CreateQuote)
- Endpoint: POST /sandbox/interpret
- Code path:
  src/server/api/sandbox.py:sandbox_interpret
  -> src/services/quote_service.py:make_draft
  -> free_text_interpreter.py:interpret_free_text
  -> mappings/*.yaml (patterns/tasks)
  -> src/services/atl_lookup.py:get_atl_time_minutes (ATL time lookup)
  -> src/services/pricing.py:get_price (material pricing)

Runtime notes:
- free_text_interpreter returns **1 task per segment** (deterministisk match).
- Runtime uses the shared mappings loader: src/services/task_library.py:load_all_tasks_from_mappings.
- Each ATL-backed task now includes **atl_variant_options** (UI-underlag för att välja variant).

### Quotes draft + persistence (available)
- Endpoint: POST /quotes/draft
  -> src/services/quote_service.py:make_draft
- Endpoint: POST /quotes
  -> src/services/quote_service.py:create_quote
  -> src/server/models/{quote.py, customer.py}

### Material mode (Lovable CreateMaterialQuote)
- Endpoint: POST /quotes/material-draft
- Code path:
  src/server/api/quotes.py:quote_material_draft
  -> src/services/quote_service.py:material_draft
  -> src/services/work_profiles.py (work_profiles.yaml loader)
  -> src/services/pricing.py:get_price

### Material parse (used by frontend parse flow)
- Endpoint: POST /quotes/material-parse
- Implementation currently lives in:
  src/server/api/quotes.py:quote_material_parse
- Note: duplicates parts of pricing/map lookup logic (tech debt).

## Admin-only / Sandbox tooling (used intentionally)

### Read-only ATL helpers for UI (no writes)
- POST /sandbox/atl-variant-preview
  - Input: { moment, variant }
  - Output: minutes_per_unit + variant_options
- POST /sandbox/atl-time-calc
  - Input: { moment, variant, quantity }
  - Output: minutes_per_unit + minutes_total (+ variant_options)

### Accept/apply ATL ref to mappings (writes YAML + backup) — GUARDED
- Endpoints:
  POST /sandbox/atl-apply-preview (read-only)
  POST /sandbox/atl-apply-confirm (writes YAML; blocked in prod unless DOCKIT_ALLOW_MAPPING_WRITES=true)
- Code path:
  src/server/api/sandbox.py
  -> src/services/atl_apply.py (backup + write + verify)

### GPT helper endpoints (Sandbox only)
- /sandbox/gpt-workplan
- /sandbox/gpt-match-tasks
- /sandbox/gpt-suggest-tasks
- /sandbox/gpt-match-atl
- /sandbox/gpt-atl-rank
(These are admin/sandbox utilities; not the runtime path for /sandbox/interpret.)

## Not wired / legacy / experimental (NOT used by any API router)
These files are present but are not imported by src/server/api/* routes:

- src/server/services/dockit_task_mapper.py
  (Uses knowledge/dockit/dockit_custom_mapping.yaml and loaders; not in production path)

- src/server/loaders/atl_loader_new.py
- src/server/loaders/atl_loader.py
- src/server/loaders/atl_loader_backup.py
  (Loader experiments for ATL search; currently not used by API routes)

## Known duplication / tech debt (do not refactor in cleanup step 1)
- Task loader exists in two places:
  - free_text_interpreter.py:_load_all_tasks_from_mappings
  - src/services/task_library.py:load_all_tasks_from_mappings
  (Risk: divergence. Consolidate later.)

- ATL runtime source is now:
  knowledge/atl/compiled/atl_total.csv
  (Nav-layer per chapter is not implemented/wired in code right now.)

- src/services/quote_service.py contains duplicated helper definitions / legacy paths.
  (Cleanup later; avoid behavior changes early.)

## Cleanup policy
- Step 1 cleanup = documentation + labeling only (no behavior change).
- Any consolidation/refactor must be preceded by: grep/search for imports + a minimal smoke test run.


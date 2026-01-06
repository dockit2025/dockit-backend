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
  -> src/services/favorites.py (customer favorites)

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
- Note: this endpoint duplicates price/map lookup logic instead of reusing src/services/pricing.py.

## Admin-only / Sandbox tooling (used intentionally)
### Accept/apply ATL ref to mappings (writes YAML + backup)
- Endpoints:
  POST /sandbox/atl-apply-preview
  POST /sandbox/atl-apply-confirm
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

## Known duplication / tech debt (do not change in cleanup step 1)
- Task loader exists in two places:
  - free_text_interpreter.py:_load_all_tasks_from_mappings
  - src/services/task_library.py:load_all_tasks_from_mappings
  (Risk: divergence. Cleanup later should consolidate.)

- ATL source used in current code paths points to:
  knowledge/atl/Del7_ATL_Total.csv
  (Compiled + nav architecture described in Master Prompt is not active in code right now.)

- src/services/quote_service.py contains duplicated helper definitions (_estimate_task_time_minutes defined multiple times).
  (Cleanup later; avoid changing behavior in early cleanup.)

## Cleanup policy
- Step 1 cleanup = documentation + labeling only (no behavior change).
- Any consolidation/refactor must be preceded by: grep/search for imports + a minimal smoke test run.

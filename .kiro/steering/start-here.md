---
inclusion: auto
name: start-here
description: Starting point and orientation for any new session on this repo
---

# Start Here — ff-consumer

You are working on the **Flavor Find Consumer Backend** (`ff-consumer`).

## What to read first (in order)

1. **This file** — orientation
2. `decisions.md` — all product and technical decisions already made; don't re-ask these
3. `project-overview.md` — what this repo is, the two-system rule, stack, staging server
4. `engine-api-contract.md` — every engine endpoint, request/response shapes, caching and resilience rules
5. `architecture.md` — Django apps, full data model, auth design, Free vs Plus gating
6. `engine-reference.md` — engine internals, exact package versions, CI/CD and deploy patterns to copy
7. `sprint-plan.md` — 5 iterations, what to build when, exit criteria

## Current state of the repo

The repo was just created. It contains only:
- The consumer backend architecture PDF
- The master plan PDF
- This `.kiro/steering/` documentation

**No code exists yet.** Iteration 1 starts next.

## What to build in Iteration 1

See `sprint-plan.md` → Iteration 1 checklist. The first task is:

1. Bootstrap the Django project from the engine's structure (same layout, same tooling, same CI)
2. Build `core` and `accounts` apps
3. Build the `engine_client` app — the consumer backend's only route to food data
4. Get to: register → login → call engine → see `dataset_version` in response

## The one rule that matters most

**The consumer backend never reads the engine's database.**
All food data — dishes, ingredients, pairings, substitutions, regions — comes from `engine.flavorfind.co.ke/v1/`.
The engine client in `apps/engine_client/` is the only place engine calls are made.

## Engine is live and ready

```
URL:    https://engine.flavorfind.co.ke
Health: GET https://engine.flavorfind.co.ke/v1/health/
Docs:   https://engine.flavorfind.co.ke/docs/
Server: ssh -o StrictHostKeyChecking=no mayday@100.96.139.83
Path:   /home/mayday/ff-engine
```

The consumer backend will deploy alongside the engine on the same server at `/home/mayday/ff-consumer`.

## Key numbers

- Engine dataset version: `2026.10.0`
- Engine version: `1.0.0`  
- Plus price: KES 199/month
- Search p95 target: < 250 ms (engine < 150 ms + consumer overhead)
- Coverage gates: 85% overall, 95% for `accounts`, `billing`, `engine_client`
- Python: 3.12 | Django: 5.2.x | DRF: 3.18.x | PostgreSQL: 16

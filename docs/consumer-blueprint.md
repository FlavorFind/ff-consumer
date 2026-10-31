# FLAVOR FIND | CONSUMER BACKEND DOCUMENT

## Consumer Backend Blueprint
### How the Flavor Find consumer backend works, and how we build it

**Understand the backend in plain language, with no code**
**15 parts | 47 build steps | 5 iterations | ~40-case safety test**

*Draft v1 | October 2026 | Nairobi, Kenya | Confidential*

---

## Part I: How the Consumer Backend Works

---

### 1. The Answer, and What This Document Is

Yes. The engine is done. The consumer backend is next. It is the right second step because:

- The engine knows food. This backend knows people. One without the other cannot make a product.
- The app teams (website, Android) have nothing to call until this backend exists.
- Revenue only starts when billing works. The engine has no billing.
- Data about real users — what they cook, what they save, how they search — feeds back into making the engine better.

This document explains the consumer backend so that anyone on the team can understand the entire system by reading it, with no code. It explains what each part does, how the parts connect, how the search works, how money flows, how data stays safe, and the exact order in which we build it.

| Part | What you will find | Sections |
|---|---|---|
| I. How it works | What it is, the fourteen parts, how search works, how money works, how sync works | 2 to 15 |
| II. Building it | The 47 build steps in order, grouped into five iterations | 16 to 17 |
| III. Quality and ops | What correct means, the safety test, how it scales | 18 to 20 |
| IV. Reference | FAQ and glossary | 21 to 22 |

The companion document, **Consumer Backend Sprint Architecture**, covers the technical side: data model, repository setup, CI/CD pipelines, security, 2FA, infrastructure, and the full iteration plan with DevOps and security tasks.

---

### 2. The Consumer Backend in One Page

The Flavor Find consumer backend is a Django/DRF service that sits between the app (website and Android) and the engine. It owns everything about people. The engine owns everything about food.

```
THE CONSUMER BACKEND IN ONE PICTURE

App (website / Android)
        │
        ▼
  Consumer Backend
  ┌────────────────────────────────────────────────┐
  │  Who you are    What you have    What you do   │
  │  (accounts)     (pantry)         (saved,       │
  │                                  plans, cook)  │
  │  What you pay   What you submit  Your safety   │
  │  (billing)      (community)      (diet, privacy)│
  └────────────────────────────────────────────────┘
        │
        ▼
  Recipe Engine /v1
  (food data — the backend never reads the engine's database)
```

**What the consumer backend knows:**
- Users (identity, preferences, diet, allergens)
- Pantries (which engine ingredients a user has)
- Saved recipes, meal plans, shopping lists
- Cooking history, reviews, community submissions
- Subscriptions (Free/Plus) and payments (M-Pesa)
- Notifications and device tokens
- Offline sync state

**What the consumer backend does not know:**
- Dish recipes, steps, ingredients (lives in the engine)
- Pairings and substitutions (lives in the engine)
- Allergen facts (lives in the engine — the backend applies the user's exclusions as a filter)
- Prices on menus (lives in the hotel platform)
- Anything about other users' data (strict row-level scoping)

**What the consumer backend never does:**
- Read the engine's database
- Send user IDs, emails, or device data to the engine
- Run a search without the user's diet and allergen exclusions attached

---

### 3. The Fourteen Parts of the Consumer Backend

| # | Part | Plain-language job | Built in |
|---|---|---|---|
| 1 | Identity vault | Stores who you are and how to verify it | Iter 1 |
| 2 | Diet and profile store | Stores your food preferences, allergen exclusions, household, budget | Iter 1 |
| 3 | Engine client | The only door to the engine — one typed client, all calls go through here | Iter 1 |
| 4 | Pantry keeper | Stores which ingredients you have (as engine IDs) | Iter 2 |
| 5 | Search bridge | Wraps the engine search, injects your pantry and diet, adds personalisation | Iter 2 |
| 6 | Library | Saves recipes, organises them into collections, logs your cooking history | Iter 3 |
| 7 | Planner | Builds weekly meal plans, generates shopping lists, shares via WhatsApp | Iter 3 |
| 8 | Budget mode | Takes your KES budget and finds what you can cook within it | Iter 3 |
| 9 | Content | Taste of 47 counties stories and editorial, tied to engine region slugs | Iter 3 |
| 10 | Sync engine | Keeps the Android app's offline data in sync with the server | Iter 3 |
| 11 | Community | Recipe submissions, reviews — drafts go to the engine after moderation | Iter 4 |
| 12 | Billing | Flavor Find Plus subscription, M-Pesa Daraja payments, entitlements | Iter 4 |
| 13 | Notifications | Push, email, in-app; user preferences; quiet hours | Iter 4 |
| 14 | Safety and privacy | Consent records, data export, account deletion, audit log | Iter 4 |

---

### 4. The Identity Vault: Who You Are

Every person in the system has a user record. Everything else (pantry, plans, subscriptions) belongs to a user.

**How you prove who you are:**

| Method | How it works |
|---|---|
| Email + password | You register with an email and a password. The password is stored as a secure hash (Argon2id — the most secure algorithm available). It is never stored in plain text. |
| Phone OTP | You enter your phone number. The backend sends a 6-digit code. You have 5 minutes and 5 attempts. After that, you wait. |
| JWT tokens | After login, you get two tokens: an access token (valid for 15 minutes) and a refresh token (valid for 30 days). The access token proves who you are on every request. When it expires, the refresh token gets you a new one without logging in again. |

**Devices:**
Every login on a new device creates a device record. In your settings, you can see every device that is signed in and remove any that are not yours.

**Consent:**
When you agree to the terms of service or privacy policy, that agreement is stored with a timestamp and the version you agreed to. This is not just for legal reasons — it means you can always see exactly what you agreed to.

---

### 5. The Diet and Profile Store

This is the information that personalises everything.

| Field | What it is |
|---|---|
| Language | English or Swahili. Names of dishes and ingredients shown in your language. |
| Household size | How many people you cook for. Used in shopping lists (scales quantities). |
| Region preference | Your county or region in Kenya. The search can give a small boost to local dishes. |
| Budget per meal (KES) | How much you want to spend per serving. Used in budget mode. |
| Diet tags | Tags like "vegetarian", "halal", "gluten-free". Every one of these is sent to the engine on every search — not optional. |
| Allergen exclusions | Tags like "nut-free", "dairy-free". These are the most important. A user with nut-free set can never be shown a dish with nuts, regardless of how well it matches. |

**The safety rule:**
Diet tags and allergen exclusions from your profile are attached to every single engine search call. This is enforced in the search service, not in the API view — it cannot be accidentally bypassed. The standard allergen text appears on every response that mentions dietary information:

> *"Allergen information is for guidance only. Always confirm with the kitchen before ordering."*

---

### 6. The Engine Client: The Only Door to Food

The engine client is a typed client that wraps every call to the recipe engine. It is the only place in the codebase that talks to `engine.flavorfind.co.ke`. No other app or view imports `requests` to call the engine.

**What it does:**

| Call | What happens |
|---|---|
| Version check | On startup, fetches the current dataset version from the engine and caches it in Redis for 1 hour. Every cache key includes this version. When the version changes, engine caches are flushed. |
| Ingredient resolve | Turns free text ("nyanya", "sukuma") into engine ingredient IDs. Handles Swahili, misspellings, and ambiguous words. |
| Search | Takes ingredients + diet + mode and calls the engine. Returns tiered results (exact, can_make, almost). |
| Dish detail | Fetches a dish's full information (steps, ingredients, nutrition, tags) and caches it with an ETag. |
| Pairings | Fetches what goes well with a dish. |
| Substitutions | Fetches what can replace an ingredient in a dish. |
| Missing | Given your pantry, what do you still need to make a dish? |
| Ingredients autocomplete | Fuzzy search as you type. Cached for 10 minutes. |
| Regions | List of Kenyan regions. Cached for 24 hours. |
| Community submit | Sends an approved recipe draft to the engine using the internal key. Only called by the Celery worker, never directly from a user request. |

**What happens when the engine is slow or down:**

The engine client has a **circuit breaker**. Think of it like a fuse:
- If 5 consecutive calls fail, the circuit "opens" (trips the fuse). The engine client stops trying for 30 seconds.
- During this time, the backend serves from cache — saved recipes still work, dish pages still load, previous search results are shown.
- Every response during this period includes `"engine_status": "degraded"` so the app can show a banner.
- After 30 seconds, one request is tried. If it works, the circuit closes. If it fails, the wait resets.

This means users never see a blank screen just because the engine had a brief outage.

---

### 7. The Pantry Keeper

The pantry is the heart of the "cook with what I have" experience.

**What a pantry item stores:**
- The engine's ingredient ID (e.g. a UUID like `a3f9...`)
- The engine's ingredient slug (e.g. `sukuma-wiki`)
- A display name (e.g. "Sukuma Wiki") — cached from the engine, refreshed when the dataset version changes
- When it was added
- When it expires (optional — so you can note that your tomatoes expire Friday)

**What it does not store:**
- Quantities. The engine ignores quantities in v1. They are only kept as notes in shopping items.
- Prices. Those come from engine cost estimates, clearly labelled as estimates.

**How it feeds search:**
When you do a search, the backend takes your pantry items and resolves them to ingredient IDs (or words the engine understands), then injects them alongside whatever you typed in the search box. You never have to re-type your pantry — it is always considered.

---

### 8. The Search Bridge

The search bridge is the most important endpoint in the product. It is not a simple proxy — it adds context that makes the engine's response personal to you.

**What happens when you search:**

```
1. You type ingredients (or search from your pantry)
         │
         ▼
2. Backend: resolve each word via engine resolve()
   Any ambiguous word? → return choices to the app, not a guess
         │
         ▼
3. Backend: inject your pantry items into the ingredient list
         │
         ▼
4. Backend: inject your diet tags and allergen exclusions (non-negotiable)
         │
         ▼
5. Backend: call engine search with:
   {ingredients, mode, diet, lang, limit}
         │
         ▼
6. Engine returns tiers (exact, can_make, almost)
         │
         ▼
7. Backend: personalisation layer
   — boost dishes from your preferred region
   — sort by what you have cooked recently (less likely to repeat)
   — if sponsored slots match, insert clearly labelled
         │
         ▼
8. Return to app
```

**The three result tiers (from the engine):**

| Tier | What it means | Shown as |
|---|---|---|
| Exact | All required ingredients in your pantry | "Cook now" |
| Can make | All required ingredients present when staples (oil, salt, water) are assumed | "Cook now (uses staples)" |
| Almost | 1–2 required ingredients missing (explore mode only) | "Almost — you need X" |

**Why this matters:**
Without the diet injection, a search by someone with a nut allergy could return dishes containing nuts. The search bridge makes that impossible. The diet injection happens in the `SearchService` class, not in the API view, so it cannot be accidentally skipped.

---

### 9. The Library

The library holds everything you have saved and done.

**Saved recipes:**
When you save a dish, the backend stores:
- The engine's dish ID and slug (a reference, not a copy of the recipe)
- The dataset version at the time you saved (so we can detect if the recipe changed later)
- An optional note ("Dad's favourite", "Try with less salt")
- The collection it belongs to (optional)

**Dataset drift:**
Every night, a Celery task checks the engine for changes since the last dataset version. If a dish you saved was changed or removed, it is flagged in the app with the current version and what changed. Your saved reference is never silently deleted.

**Collections:**
A collection is a named folder of saved recipes. "Weekend meals", "Coastal favourites", "Quick under 30 minutes". You create and name them yourself.

**Cooking history:**
Every time you mark a dish as cooked, a `cook_log` entry is created. This feeds:
- The personalisation layer in search (reduces repetition of recently cooked dishes)
- Your statistics ("You've cooked ugali 12 times")
- Future recipe recommendations

---

### 10. The Planner

The planner builds a week's worth of meals and turns them into a shopping list.

**How a meal plan works:**
- A plan covers one week (Monday to Sunday), identified by ISO week (e.g. `2026-W44`)
- Each entry is one dish on one day for one meal type (breakfast, lunch, dinner, snack)
- You set the number of servings per entry
- You can have multiple dishes per meal slot

**Shopping list generation:**
When you generate a shopping list from a plan:
1. The backend collects all dish IDs from the plan
2. For each dish, it calls the engine's `missing` endpoint with your current pantry
3. The result is a deduplicated list of ingredients you need to buy
4. Each item shows a quantity note and a price estimate in KES (from engine cost data — always labelled as an estimate)

**WhatsApp share:**
`GET /v1/shopping-lists/<id>/share/` returns plain text formatted for WhatsApp. Example:

```
Flavor Find Shopping List — Week 44

☐ Sukuma wiki (500g) ~KES 30
☐ Maize flour (2kg) ~KES 140
☐ Onions (3 medium) ~KES 45

Total estimate: ~KES 215
(Prices are estimates only)
```

---

### 11. Budget Mode

Budget mode is the "cook well with KES 300" feature.

**How it works:**
1. You provide: your KES budget per meal, number of servings, and your current diet
2. The backend calls the engine search with a cost filter — it asks the engine to return only dishes whose estimated cost per serving falls within your budget
3. Results are presented in tiers, same as normal search

**Important:** All cost figures are labelled "estimate" in every response. Engine cost data is based on typical market prices that curators update periodically — they are not live prices.

---

### 12. Content: Taste of 47 Counties

The content section is the editorial and cultural heart of the product.

**What it is:**
A curated collection of stories about regional Kenyan food — one or more stories per county, written by the content team. Each story is linked to one or more engine region slugs, so a story about coastal food automatically surfaces coastal dishes.

**What it is not:**
- It is not a Wikipedia article. It is written editorial: "In Lamu, pilau is cooked with a blend of spices that..."
- It is not AI-generated. Stories are written, reviewed, and published by a human author.

**API:**
- `GET /v1/regions/` — lists all Kenyan counties and regions (proxies the engine, cached 24 hours)
- `GET /v1/stories/` — lists published stories
- `GET /v1/stories/<slug>/` — full story with the associated region and featured dishes

---

### 13. Offline Sync

The sync engine lets the Android app work without internet and resynchronise without losing data.

**How it works:**

Android keeps a local SQLite database. Every change the user makes offline (add to pantry, check off a shopping item, save a recipe) is recorded as a "change event" with a UUID and timestamp.

When the internet is available:
- `POST /v1/sync/push/` — the app sends its unsynced changes. The server applies them and returns any conflicts.
- `GET /v1/sync/pull/?since=<timestamp>` — the app fetches server-side changes since its last sync.

**Conflict rules:**
| Situation | Rule |
|---|---|
| Server changed data, app changed same data | Server wins for shared data (plans, lists) |
| User changed their own pantry item | User wins |
| User changed a personal note | User wins (last write) |
| App changes a completed shopping item | Apply as-is (no conflict possible) |

**Device tracking:**
Each device has a `last_sync_at` timestamp. The server knows what each device has already received. A fresh install on a new phone can pull everything from `since=beginning`.

---

### 14. Community: Submissions and Reviews

**Recipe submissions:**
Any user can submit a recipe. The submission stays in a "draft" status in the consumer backend. It goes through the moderation queue. If a moderator approves it, a Celery worker forwards it to the engine's `POST /v1/internal/submissions/` using the internal API key. The engine then handles its own review and verification workflow.

**What the user sees:**
- `GET /v1/submissions/` — their own submissions and their status (draft, sent, in_review, accepted, rejected)
- `GET /v1/submissions/<id>/` — detail including any rejection reason

**Reviews:**
Users can rate and review dishes. Reviews go through a moderation queue before being visible. Approved reviews appear on dish pages. Stars are aggregated into a rating.

---

### 15. Billing: Flavor Find Plus

**The plans:**

| Plan | Price | What you get |
|---|---|---|
| Free | KES 0 | Search, dish pages, pantry, save up to 20 recipes, community submissions, ads |
| Plus | KES 199/month | Everything free, plus: meal plans, shopping lists, nutrition details, budget mode, offline sync, no ads, unlimited saves |

**How payment works (M-Pesa):**

```
1. You tap "Subscribe to Plus"
         │
         ▼
2. Backend calls Daraja API → you get an M-Pesa prompt on your phone
         │
         ▼
3. You enter your M-Pesa PIN and confirm
         │
         ▼
4. Daraja sends a callback to the backend at POST /v1/mpesa/callback/
         │
         ▼
5. Backend checks:
   a. Is this request from Safaricom's IP range? (Yes → continue)
   b. Does the signature match? (Yes → continue)
   c. Does the amount match what the user agreed to? (Yes → continue)
   d. Has this transaction reference already been processed? (No → continue)
         │
         ▼
6. Payment marked confirmed, Plus activated, audit event logged
         │
         ▼
7. App shows "Welcome to Plus!"
```

**What cannot happen:**
- The callback amount cannot be trusted alone. If someone sends a callback claiming a KES 1 payment for a KES 199 subscription, steps 5c catches it.
- Duplicate callbacks (Daraja sometimes sends the same callback twice) are silently ignored in step 5d.
- Card data is never stored. Ever. M-Pesa is PIN-based, and the PIN never touches our servers.

**Entitlement checks:**
Every gated endpoint (meal plans, shopping lists, nutrition details, budget mode, sync) checks if the user has an active Plus subscription before proceeding. This check happens in one place — a single `entitlements.py` module — not scattered across views.

---

## Part II: Building the Consumer Backend

---

### 16. Build Principles

- **Thin slices:** always a deployed, working backend. Every two weeks, something new is in staging.
- **Safety first:** diet/allergen injection and the permission tests are in CI from Iteration 1. They cannot be switched off.
- **Engine as a dependency, not a bloat:** the consumer backend calls the engine, it does not duplicate it. If something belongs in the engine, it goes there.
- **Test the money:** billing and payment paths have the most test coverage of anything in the system.
- **Demo every iteration:** at the end of each two weeks, a real user flow is demonstrated end-to-end in staging.
- **No step is finished until it is deployed to staging and its check passes.**

---

### 17. The 47 Build Steps in Order

Five iterations of two weeks. One to two developers, part-time content team. Estimates to validate in Iteration 1.

---

#### Iteration 1: Foundations (Weeks 1–2)

Goal: A deployed skeleton. Users can register, log in, and see `dataset_version` from the engine.

| Step | What we do | What exists afterwards | How we know it works |
|---|---|---|---|
| C1 | Create repository from engine template, protect main | ff-consumer repo with CI skeleton and rules | First PR must pass checks to merge |
| C2 | Local environment with docker-compose | One-command start: web + db + redis + worker | A new developer is running in under 15 minutes |
| C3 | Django project with split settings | Running service with health and version pages | `GET /v1/health/` green in CI |
| C4 | `core` app: `TimeStampedModel`, request ID middleware, error format, pagination | Base that every app inherits | Error format consistent across all endpoints |
| C5 | `accounts` app: `CustomUser`, email+password registration, login, JWT tokens | Working auth endpoints | Register, login, refresh, logout flow works end-to-end |
| C6 | Phone OTP: request + verify endpoints | Second login method | OTP rejects replays, expired codes, too many attempts |
| C7 | Device registration | Device table populated on login | Remote logout revokes tokens for that device |
| C8 | `profiles` app: `Profile`, `ProfileDiet` | `PATCH /v1/me/profile`, `PATCH /v1/me/diet` | Diet tags stored and returned correctly |
| C9 | `engine_client` app: typed client, health ping, version fetch | `GET /v1/meta/version/` returns engine dataset_version | Version visible in staging response |
| C10 | Engine client: circuit breaker skeleton, cache layer | Degraded mode returns `engine_status: degraded` | Simulate engine down locally, see degraded response |
| C11 | Staging deploy: Render + self-hosted server | Public staging URL | Merge to main deploys; first rollback practised |
| C12 | Staff admin with 2FA | Curator, moderator, admin roles with mandatory 2FA | Login without 2FA is impossible |

**Iteration 1 exit check:**
Register a user → set a diet → log in → call `GET /v1/meta/version/` → see `dataset_version` in the response. First rollback practised.

---

#### Iteration 2: Search and Pantry (Weeks 3–4)

Goal: Core product works. User with a pantry can search for what to cook.

| Step | What we do | What exists afterwards | How we know it works |
|---|---|---|---|
| C13 | `pantry` app: `GET`, `POST`, `DELETE /v1/pantry/<id>/` | Pantry CRUD | User can add and remove ingredients |
| C14 | Engine client: `resolve()` | Ingredient resolution with ambiguity handling | "unga" returns options, never a guess |
| C15 | Engine client: `search()` with diet injection | Full search pipeline | Diet always sent; unfiltered search impossible |
| C16 | Ambiguity flow: return choices to client | `POST /v1/resolve/` endpoint | Ambiguous input prompts choice picker |
| C17 | `POST /v1/search/` with pantry injection | Personalised search | Pantry items injected automatically |
| C18 | `GET /v1/ingredients/` autocomplete | Debounced autocomplete endpoint | Returns results in < 100 ms (cached) |
| C19 | `GET /v1/dishes/<slug>/` proxy + ETag cache | Dish detail pages | Cache hit on second request |
| C20 | Engine cache: Redis keyed by SHA256 | Search results cached | Same query returns same result from cache |
| C21 | Circuit breaker: full implementation | Engine-down degraded mode | Simulate 5 failures; circuit opens; degraded response |
| C22 | Safety golden set v0 (~20 cases) in CI | Automated allergen + diet test | CI fails if vegetarian profile sees meat |
| C23 | Rate limits per user and per IP | 429 responses with Retry-After | Burst test shows correct throttling |
| C24 | Permission tests: cross-user pantry access | Automated test | User A cannot see or modify user B's pantry |

**Iteration 2 exit check:**
Pantry search returns tiers with explained reasons. "unga" asks. Vegetarian profile never returns meat. Excluded allergen never appears. Engine-down fallback shows `engine_status: degraded`.

---

#### Iteration 3: Library, Planner, Offline, Content (Weeks 5–6)

Goal: Users can save recipes, plan a week, generate a shopping list, sync offline, and read regional stories.

| Step | What we do | What exists afterwards | How we know it works |
|---|---|---|---|
| C25 | `library` app: `SavedRecipe`, `Collection` — CRUD + `POST /v1/cooked/` | Save and organise recipes | Save, move to collection, unsave all work |
| C26 | Dataset drift check: nightly Celery task | Flagged recipes when engine version changes | Simulate version bump; flag appears |
| C27 | `planner` app: `MealPlan`, `MealPlanEntry` | `GET/PUT /v1/plans/<week>/` | Create and retrieve a full week plan |
| C28 | Shopping list generation from plan | `POST /v1/plans/<id>/shopping-list/` | List contains only what user doesn't have in pantry |
| C29 | Shopping item check/uncheck | `PATCH /v1/shopping-lists/<id>/items/<item_id>/` | Checked items persist |
| C30 | WhatsApp share text | `GET /v1/shopping-lists/<id>/share/` | Returns plain text ready to paste into WhatsApp |
| C31 | `budget` app: `POST /v1/budget/suggest/` | Budget mode endpoint | KES 300 budget returns dishes within cost estimate |
| C32 | `content` app: `Story` model, admin entry | `GET /v1/stories/`, `GET /v1/stories/<slug>/` | Stories visible in API |
| C33 | `GET /v1/regions/` proxying engine | Regions list cached 24 h | Returns all Kenyan counties |
| C34 | `sync` app: `POST /v1/sync/push/`, `GET /v1/sync/pull?since=` | Offline sync endpoints | Sync two "devices" without data loss |
| C35 | Audit log: append-only `AuditEvent` shipped via Celery | Audit trail for sensitive actions | Delete account → audit event appears in external store |

**Iteration 3 exit check:**
Plan a full week → generate shopping list → check off items → share WhatsApp text. Edit pantry on two API tokens → sync without data loss. At least 3 stories visible.

---

#### Iteration 4: Community, Money, Notifications (Weeks 7–8)

Goal: Users can submit recipes, pay for Plus, and receive notifications.

| Step | What we do | What exists afterwards | How we know it works |
|---|---|---|---|
| C36 | `community` app: `POST /v1/submissions/`, `GET /v1/submissions/` | Submission CRUD | User sees their own submissions and status |
| C37 | `POST /v1/dishes/<slug>/reviews/` | Review submission + moderation queue | Review queued; not public until approved |
| C38 | Moderation queue + Celery worker: approved submission → engine | `moderation` app + worker | Approve in admin → Celery forwards to engine internal endpoint |
| C39 | `billing` app: `GET /v1/plans/`, `GET /v1/subscription/` | Plan and subscription info | Free and Plus plans returned correctly |
| C40 | M-Pesa STK push: `POST /v1/subscribe/` | Payment initiation | Sandbox STK push triggered |
| C41 | M-Pesa callback: `POST /v1/mpesa/callback/` with all safety checks | Plus activation flow | Duplicate callback ignored; wrong amount rejected; Plus activates on confirmed payment |
| C42 | Entitlement checks on gated endpoints | Meal plans and shopping lists return 403 for Free users | Free user cannot access Plus features |
| C43 | Renewal reminders + expiry checks via Celery beat | Automated subscription lifecycle | Expiry correctly detected and handled |
| C44 | `notifications` app: push registration, in-app table, preferences | `POST /v1/devices/` + notification CRUD | Device token stored; in-app notification created |
| C45 | `GET /v1/me/export` | User data export | Returns all user's data as JSON |
| C46 | `DELETE /v1/me` with grace period purge | Account deletion | Soft delete immediate; purge after grace period |
| C47 | Consent records stored and queryable | Consent audit trail | Consent stored on registration; queryable by staff |

**Iteration 4 exit check:**
Pay with M-Pesa sandbox → Plus activates → meal plans unlock. Submit a recipe → approve in admin → Celery forwards to engine. `DELETE /me` → purge after grace period → audit event logged.

---

#### Iteration 5: Hardening and Release (Weeks 9–10)

Goal: v1.0.0. Production-ready. App teams integrated.

| Step | What we do | What exists afterwards | How we know it works |
|---|---|---|---|
| Bug fixes | Fix issues found in iterations 1–4 | Stable codebase | All CI checks green |
| Performance | Identify and fix N+1 queries; query count budgets | All endpoints within query budget | Load test: search p95 < 250 ms at 50 req/s |
| Load test | 50 req/s sustained on staging | Load test report | p95 < 250 ms |
| Soak test | 2-hour sustained load | Soak test report | No degradation after 2 hours |
| Pen test | External penetration test on staging | Test report | All high/critical findings fixed |
| Backup drill | Restore staging DB from backup, verify integrity | Drill record | Data intact after restore |
| Rollback drill | Deploy RC1, roll back to previous, verify health | Drill record | Health check passes after rollback |
| Incident tabletop | Simulate engine outage, payment callback failure | Exercise notes | Team knows what to do |
| Runbooks | Write all runbooks in `docs/runbooks/` | Complete runbooks | Another developer can follow them |
| API freeze | No breaking changes after this point for v1 | Frozen API contract | Version locked |
| App integration | Website and Android teams integrate using generated clients | End-to-end integration | App teams can integrate in under a day |
| v1.0.0 release | Tag and deploy to production | v1.0.0 live | All exit criteria met |

**Iteration 5 exit check:**
All exit criteria in the sprint architecture document met. Website and Android integrated. v1.0.0 tagged and live.

---

## Part III: Quality and Operations

---

### 18. What "Correct" Means: The Safety Golden Set

The golden set is a list of approximately 40 test cases that define correct behaviour for safety-critical scenarios. It runs on every code change, every configuration change, and every search-related change. It must be 100% passing before any code can merge.

| Category | Cases | What it protects |
|---|---|---|
| Allergen exclusion | 10 | An excluded allergen never appears in search results, regardless of match score or tier |
| Vegetarian | 5 | A vegetarian profile never returns meat, fish, poultry, or seafood dishes |
| Other diet tags | 5 | Halal, gluten-free, nut-free tags filter correctly |
| Ambiguity | 5 | "unga", "pepper", "nyama" return choices to the app, never a silent guess |
| Swahili / Sheng input | 5 | nyanya → tomato, sukuma → sukuma wiki, chapati resolves correctly |
| Explore mode | 5 | "Almost" results named correctly; not shown in strict mode |
| Allergen disclaimer | 5 | Every response that mentions dietary data includes the standard disclaimer text |
| **Total** | **~40** | |

A golden case looks like this:

```yaml
id: allergen-001
description: User with nut-free exclusion never sees nut-containing dishes
diet_profile: ["nut-free"]
query: {ingredients: ["chicken", "rice"], mode: "strict"}
must_never_include: any dish with ingredient_slug in ["peanuts", "groundnuts", "cashews", ...]
```

Every real incident (wrong result, allergen appeared in results, ambiguous word silently resolved) becomes a new golden case. Over time, the golden set becomes the written definition of "safe" for this product.

---

### 19. Running and Scaling the Backend

| Stage | Setup | Move to next when |
|---|---|---|
| 1. Launch | 1–2 Render instances, managed Postgres, managed Redis | Sustained above 60% capacity |
| 2. Growth | 2–3 instances, connection pooling (PgBouncer) | DB CPU regularly high or p95 slipping |
| 3. Scale | Separate read replica for reporting queries | Read load dominates |
| 4. Database | Revisit schema for high-volume tables (cook_log, audit_event) | Table scans taking > 100 ms |

The design target is 100,000 active users before any major redesign is needed. At launch, the load is tiny — a well-configured single Render instance handles it easily.

---

### 20. How the Consumer Backend Grows After v1.0

| Version | Possible additions |
|---|---|
| v1.1 | TOTP 2FA option for end users; Google OAuth login; recipe images (hosted externally) |
| v1.2 | AI cooking buddy (Celery task calling LLM, engine as tools); dietary tracking over time |
| v1.3 | Friends / household accounts (shared pantry, shared meal plan) |
| v1.4 | Affiliate ordering: "add these ingredients to your Jumia/Twiga cart" |
| v2.0 | Multi-currency, multi-country (Uganda, Tanzania); M-Pesa alternatives |

---

## Part IV: Reference

---

### 21. Frequently Asked Questions

| Question | Answer |
|---|---|
| What if the engine is down? | The backend serves from cache. Recent search results, saved recipes, and dish pages continue to work. The engine_status field in responses says "degraded" so the app can show a banner. |
| What if a dish I saved was changed in the engine? | The nightly drift check detects it and flags the saved recipe. The app shows the current version and notes that the recipe changed. |
| Can a Free user see Plus features? | No. Every gated endpoint checks entitlements before returning data. Automated tests verify this cannot be bypassed. |
| What if M-Pesa sends the callback twice? | The provider_ref is a unique idempotency key. The second callback is silently ignored and returns HTTP 200 to Daraja. |
| What if my allergen is not filtered? | This cannot happen if the system is working correctly. The safety golden set in CI specifically tests this. If the golden set is green, allergens are filtered. If it is not green, the build fails and no code can merge. |
| What if a user tries to access another user's data? | The permission tests in CI specifically test this. Every queryset is filtered by user. A test that tries cross-user access must fail — if it doesn't, the build fails. |
| Can I use the engine directly without the consumer backend? | Yes — with your own API key from the engine admin. But you would not have pantry, plans, subscriptions, or personalisation. Those all live in the consumer backend. |
| How does the "unga" ambiguity work? | When you type "unga", the engine returns `status: ambiguous` with options (maize flour, wheat flour, millet flour). The consumer backend passes these choices to the app. The app shows a picker. You choose. Only then does the search proceed. Never a silent guess. |
| What language do responses come in? | You set your language (English or Swahili) in your profile. The `lang` parameter is included in every engine call. Dish names, ingredient names, and steps come back in your language where a translation exists; English otherwise. |

---

### 22. Glossary

| Term | Meaning |
|---|---|
| Engine | The standalone Recipe Engine service at engine.flavorfind.co.ke. Knows food. Does not know users. |
| Consumer backend | This service (ff-consumer). Knows users. Calls the engine for all food data. |
| Two-system rule | The consumer backend calls the engine's API. It never reads the engine's database. |
| Pantry | A user's list of engine ingredient IDs — what they have at home. |
| Tier | Exact, can_make, or almost — how well a dish fits what a user has. |
| Strict mode | Only dishes that need nothing more than what the user has (default search mode). |
| Explore mode | Also shows "almost" dishes missing one item, labelled clearly. |
| Dataset version | A numbered snapshot of the engine's knowledge (e.g. 2026.10.0). Included in every cache key. |
| Circuit breaker | A fuse that stops calling the engine after repeated failures; serves from cache during outage. |
| Allergen exclusion | A diet tag on a user's profile that is always sent to the engine and always filters results. |
| Safety golden set | ~40 test cases that run on every code change; must be 100% for any merge to succeed. |
| JWT access token | A short-lived (15 min) proof of identity, sent in every API request. |
| JWT refresh token | A long-lived (30 day) token used to get new access tokens without logging in again. |
| Argon2id | The password hashing algorithm used for all user passwords — the most secure available. |
| OTP | One-time password sent to a phone number for login; 6 digits, 5 minutes, 5 attempts max. |
| Entitlement | Whether a user has the right to use a feature (based on their plan). |
| Idempotency key | A unique identifier (provider_ref) that ensures a payment callback is processed only once. |
| Drift detection | The nightly check that finds saved recipes whose engine dish changed since they were saved. |
| Audit event | An append-only record of a sensitive action (e.g. delete account, approve submission). Shipped to an external log store. |
| Row-level scoping | Every database query is filtered by `user=request.user`. Enforced in code + verified by automated tests. |
| Grace period | The delay between soft-deleting an account and permanently purging the user's data. |
| 2FA | Two-factor authentication. Staff must use an authenticator app or hardware security key. No SMS codes. |
| Celery | The background task runner. Handles: notifications, sync, billing renewals, drift checks, audit log shipping. |
| Engine client | The single typed client (in `apps/engine_client/`) through which all engine calls are made. |
| Degraded mode | The state when the engine circuit is open; the backend serves from cache + adds `engine_status: degraded`. |

---

*If you remember one thing: the consumer backend is the trusted layer that knows its users, protects their data, enforces their dietary safety, and calls the engine honestly. Build it with the same care as the engine — because from the user's perspective, it is the product.*

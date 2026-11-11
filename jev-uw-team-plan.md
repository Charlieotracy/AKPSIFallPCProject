# Jev UW Scheduling Agent: Team Plan

## What we're building

An assistant for UW-Madison scheduling: booking UHS appointments, reserving CBTF exam slots, finding football/basketball tickets, and finding courses with open seats. The user asks in plain language; the assistant finds options, ranks them against the user's schedule and preferences, and books the one they confirm.

**The split:**
- **Jev** is the decision engine. It answers bounded questions (pick an option, score this, is this true) and returns probabilities. It doesn't write text.
- **An LLM** handles conversation and any text typed into forms.
- **The extension and backend** do the clicking, searching, and watching.

## Platform: Chrome extension (MV3) + Python backend

The deciding factor is login. MyUHS, PrairieTest, Course Search & Enroll, and the UW Badgers ticket account all require NetID + Duo, so booking must happen inside a logged-in session.

| | Chrome extension | Website | Swift (iOS) app |
|---|---|---|---|
| Acting on NetID/Duo sites | Works in the user's own tabs; user does Duo normally | Can't touch other sites; needs server-side headless browsers logged in as each user | Possible via web view + injected JS, but clunky and fragile |
| Credentials | Never leave the browser | We'd hold NetID sessions/passwords. Bad idea. | Sessions live in the app |
| Background watching | Only while browser is open (`chrome.alarms`); public-data watchers run on backend 24/7 | Easy 24/7 | iOS limits background work; needs server push |
| Build effort (6 people) | TypeScript + React, familiar to most | Easiest | Needs Swift, Macs, $99/yr Apple dev account |
| Reach | Any Chromium browser (Chrome, Edge, Brave, Arc) | Anyone | iPhone only |
| Demo | Load unpacked | Share a URL | TestFlight invite |

The extension gets real sessions for free and keeps the user in control, since everything happens in visible tabs.

**Note:** Browser Use and Stagehand drive their own Playwright browser and won't run in an extension. We'll borrow their loop (observe page → list interactive elements → Jev picks one → act → repeat) and build a small version in content scripts.

**Stretch:** Safari support via converting to a Safari web extension in Xcode.

## Architecture

```
Chrome extension (user's browser)
  side panel UI  <->  service worker  <->  content scripts (one per site)
                           |
                           |  HTTPS + WebSocket, per-user token
                           v
Backend (FastAPI)
  orchestrator LLM | Jev wrapper | risk gate
  task store (Postgres) | watchers (scheduler) | notifications | calendar
                           |
                           v
  TypeSafe Jev API, LLM API, public.enroll.wisc.edu, public ticket listings
```

- **Side panel:** chat UI. Holds the WebSocket while open, since MV3 service workers get suspended when idle.
- **Service worker:** routes messages, opens/reuses tabs, runs alarm-based checks.
- **Content scripts:** read pages, build snapshots, perform actions. Four allowed domains only.
- **Backend:** holds Jev and LLM API keys (never shipped in the extension), runs the orchestrator, stores tasks, runs public-data watchers, sends notifications.

**Stack**
- Extension: TypeScript, React, WXT, Tailwind
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy, Postgres (SQLite locally), APScheduler, langchain-typesafe or direct HTTP for Jev, Claude or OpenAI SDK
- Watch Service: Java 21, Spring Boot (services/watch-service/)
- Hosting: Render, Railway, or Fly

## Request flow

Example: *"Book my CS 354 midterm at the CBTF Thursday after 2."*

1. **Route.** Side panel → `POST /chat`. Jev `route` choice → `cbtf`.
2. **Extract.** LLM fills the CBTF schema (CS 354, midterm, Thursday ≥ 2:00 PM) → Task.
3. **Readiness.** Jev `ready` noul. If low confidence, LLM asks one follow-up ("Midterm 1 or 2?"); task waits in `needs_info`.
4. **Search.** Backend sends `run_adapter(search)`. Service worker opens/reuses a PrairieTest tab; content script checks login. If signed out, side panel asks the user to sign in and the task waits.
5. **Extract candidates.** Content script pulls available slots as `Candidate` objects.
6. **Rank.** Backend checks against busy times and preferences; Jev `rank_fit` scores each. Side panel shows the top three as cards.
7. **Confirm.** User picks a card; backend issues a confirm token tied to it.
8. **Book.** `adapter.book(candidate, token)`. Before every click/submit, Jev `is_commit` runs. Commits need a matching token; unplanned commits are blocked. Code enforces this, Jev only advises.
9. **Verify.** Jev `success` noul checks the result page. Reservation details are stored, shown with an `.ics` download, and a notification goes out.

**Task states:** `received → routed → needs_info ⇄ (user reply) → ready → searching → candidates → awaiting_confirm → executing → done`. Any state can go to `failed` or `handed_off` (assistant can't finish, gives the user the next step, e.g. UHS types that require a phone call).

**Watch tasks:** `ready → watching → triggered → candidates → ...`, then as normal.

## Where Jev fits

Adapters are mostly scripted with known selectors (faster, more reliable). Jev handles judgment calls and is the fallback navigator when a selector breaks.

| Question | Type | When | Decides |
|---|---|---|---|
| `route` | choice | Every new message | Module: courses, uhs, cbtf, tickets, other |
| `ready` | noul | After parameter extraction | Search now or ask a follow-up |
| `page_state` | choice | Each adapter step | login_required, expected_page, error, unexpected |
| `next_action` | choice | Only when a selector fails | Which indexed element to act on, or stop |
| `rank_fit` | score | Per candidate | Ordering shown to user |
| `is_commit` | noul | Before any click/submit | Whether a confirm token is required |
| `success` | noul | After a commit | Whether the action went through |

**Thresholds:** start at ~0.8 as a placeholder; real values come from week 5 evals. Below threshold: ask the user, fall back to the LLM, or stop. For `is_commit`, false positives (extra confirmations) are fine; misses are not.

**Hard rules (in code, not models):**
- Domain allowlist in the manifest
- Commits require a matching confirm token
- Step budget of ~25 actions per run
- Never type into a password field
- Never auto-buy tickets

## Modules

**Courses** (easiest; search needs no login)
- Unauthenticated JSON search at `https://public.enroll.wisc.edu/api/search/v1` (what the public page calls; undocumented, may change). Cache and poll politely.
- Seat availability is real time, so the seat watcher runs on the backend and notifies when a section opens.
- Enrolling happens in the logged-in enroll app: extension adds to cart; final enroll click goes through the confirm gate.

**UHS** (MyUHS, NetID)
- Only some appointment types are bookable online; UHS withholds others and tells students to call **608-265-5600**. If not bookable, go to `handed_off` and show the number.
- Health data rules:
  - Send the visit reason to the LLM only to pick the appointment category
  - Never store UHS page snapshots
  - Log decisions without page content
- Opening watcher only works while the browser is open.

**CBTF**
- Most CBTFs use PrairieTest (`us.prairietest.com`), but **UW's system is unconfirmed. Charlie (P6) checks in week 1 before building the adapter.**
- Find UW's cutoff for reservation changes before an exam and enforce it in the adapter.
- Popular slots fill fast; add a slot-opening watcher.

**Tickets**
- Student tickets go through the official UW Badgers account; all transfers go through the UW Badgers app.
- Module is a watcher over public resale listings that alerts with a link. Never buys. Point users to the official transfer flow to avoid scams.

## Team roles

| Role | Person |
|---|---|
| P1: Frontend | Arya |
| P2: Backend core + tech lead | Krishiv |
| P3: Backend services | Rohan |
| P4: Agent (orchestrator LLM) | Jeffrey |
| P5: Agent (Jev layer + evals) | Ari |
| P6: Integrations | Charlie |

P2 is tech lead and owns the core data models and interfaces.

**P1: Frontend (extension UI)** — Arya
- Side panel chat (React/WXT), candidate cards, confirm dialog
- Progress view ("Opening PrairieTest... found 6 slots")
- Watches page (list, pause, delete); settings (preferred times, notification channel, linked calendar)
- Permissions onboarding screen; login-required prompt
- **Week 1:** side panel shell talking to a mocked backend over real message types
- Works with: P2 (API/events), P4 (reply wording), P6 (manifest/packaging)

**P2: Backend core + tech lead** — Krishiv
- FastAPI routes: `/chat`, `/tasks`, `/watches`, `/decide`, `/confirm`, WebSocket
- Pydantic models as single source of truth → JSON Schema → generated TS types
- DB schema, task state machine, user accounts (invite codes OK for MVP)
- Confirm token issuing/checking; CI and deployment; merges all `shared/schemas` changes
- **Week 1:** repo, CI, schemas v1, deployed `/health`
- Works with: everyone, mostly P1, P4, P5

**P3: Backend services (watchers, notifications, calendar, tickets)** — Rohan
- Scheduler; course seat and ticket listing watchers (dedupe, rate limits, backoff, jitter)
- Tickets module end to end (public resale listings watcher + alert links; no logged-in flow)
- Notifications: Chrome (via extension) and email
- Calendar: `.ics` export for MVP; stretch: busy times from Google Calendar / Outlook (Microsoft Graph)
- Conflict-check helper for ranking
- **Week 1:** scheduler running a dummy job; public course API client with tests
- Works with: P2, P5 (ranking), P6 (courses)

**P4: Agent (orchestrator LLM)** — Jeffrey
- Routed message → module parameter schema (structured output)
- Follow-up questions when `ready` is low; text adapters type into forms
- Short-term conversation context; assistant reply wording
- Prompts as versioned files in the repo; no health data in conversation history
- **Week 1:** parameter schemas for all four modules; extraction working on 20 sample messages
- Works with: P5, P1, P2

**P5: Agent (Jev layer + evals)** — Ari
- Jev client wrapper: retries, timeouts, logging, LLM-classifier fallback if Jev is down/rate-limited
- Question library, thresholds config, risk gate logic (P2 owns tokens)
- Eval harness, datasets, threshold tuning; per-call cost/latency logging
- **Week 1:** API key working, wrapper returns normalized `Decision` objects, `route` running on samples
- Works with: P4, P6; pairs with P6 on `page_state`, `next_action`, `is_commit`

**P6: Integrations (harness + logged-in adapters)** — Charlie
- Service worker ↔ content script messaging
- DOM snapshots: indexed interactive elements, trimmed text, redaction of names, IDs, DOB-like strings
- Action executor (click, type, select, wait, scroll); loop runner with step budget; domain allowlist
- Fixture recorder tool; records/scrubs fixtures for all sites; maintains `docs/site-changes.md` when selectors break
- Adapters for MyUHS, PrairieTest, and the enroll cart flow. Per site: login detection, navigation (landing → slot list → confirm), slot extraction to `Candidate`, booking with confirm token, success check, `handed_off` cases
- **Week 1:** fixtures recorded; snapshot of a saved page yields a clean element list; click on element N works on a fixture; login detection on MyUHS and PrairieTest; confirm UW's CBTF system
- Works with: P5, P1, P3

## Core data models and interfaces

**Task and candidate (Pydantic):**

```python
class Task(BaseModel):
    id: str
    user_id: str
    module: Literal["courses", "uhs", "cbtf", "tickets"]
    kind: Literal["search", "book", "watch"]
    params: dict            # validated against the module's schema, e.g. CbtfParams
    status: TaskStatus
    created_at: datetime

class CbtfParams(BaseModel):
    course: str             # "CS 354"
    exam: str | None        # "Midterm 1"
    earliest: datetime | None
    latest: datetime | None

class Candidate(BaseModel):
    id: str
    task_id: str
    label: str              # "Thu Nov 12, 2:30 PM"
    starts_at: datetime | None
    data: dict              # whatever the adapter needs to book it
    fit: float | None       # Jev rank_fit score
```

**Site adapter (TypeScript):**

```ts
interface SiteAdapter {
  module: "courses" | "uhs" | "cbtf" | "tickets";
  domains: string[];
  checkLogin(tab: TabRef): Promise<"signed_in" | "login_required">;
  search(task: Task, tab: TabRef): Promise<Candidate[]>;
  book(c: Candidate, confirmToken: string, tab: TabRef): Promise<BookResult>;
  watchCheck?(task: Task, tab: TabRef): Promise<Candidate[]>;
}
```

**Jev wrapper:**

```python
class Decision(BaseModel):
    question: str
    kind: Literal["choice", "score", "noul"]
    answer: str | float | bool
    confidence: float
    raw: dict

async def decide(state: str | dict, questions: dict[str, Question]) -> dict[str, Decision]: ...
```

Nobody calls Jev directly; everything goes through `decide()` so P5 can add logging, caching, or fallback in one place.

Raw request follows TypeSafe's published examples (model, state, named questions with type, instructions, and options for choice). Confirm exact field names and response format against TypeSafe's docs once we have a key.

```json
{
  "model": "jev-latest",
  "state": "<page snapshot or task>",
  "questions": {
    "page_state": {
      "type": "choice",
      "instructions": "Which state is this page in?",
      "options": ["login_required", "slot_list", "confirm_page", "error"]
    },
    "is_commit": {
      "type": "noul",
      "instructions": "True if clicking element 7 creates, changes, cancels, or pays for something."
    }
  }
}
```

**Extension ↔ backend messages:**
- Backend → extension: `{type: "run_adapter", task_id, op: "search" | "book" | "watch_check", payload}`
- Extension → backend: `{type: "adapter_result", task_id, candidates | result}` and `{type: "progress", task_id, step, note}`
- Mid-flow Jev decisions: content script sends a snapshot to `POST /decide`, gets a `Decision` back

## Repo layout

```
jev-uw/
  extension/
    src/sidepanel/            P1
    src/background/           P6 (service worker, alarms, messaging)
    src/content/
      harness/                P6
      enroll/                 P6
      tickets/                P3 (alert links only)
      myuhs/                  P6
      prairietest/            P6
    src/shared/types.ts       generated from shared/schemas
  backend/
    app/api/                  P2
    app/db/                   P2
    app/agent/orchestrator/   P4
    app/agent/jev/            P5
    app/watchers/             P3
    app/notify/               P3
    app/calendar/             P3
  shared/schemas/             P2 (JSON Schema exported from Pydantic)
  evals/                      P5
  fixtures/                   P6 (scrubbed page snapshots)
  docs/                       contracts.md, site-changes.md, demo-script.md
```

## How we work

- **Git:** one monorepo, protected `main`, branches `name/short-thing`, one review + squash merge per PR, schema changes need P2.
- **CI:** backend `ruff` + `pytest`; extension `eslint` + `tsc` + `vitest`; check that generated TS types match schemas.
- **Board:** GitHub Projects (Backlog, This week, In progress, Review, Done). Every issue has an owner and milestone.
- **Meetings:** weekly 30-min sync (demo what works, plan next week). Async standup Mon/Wed/Fri in group chat: done, doing, blocked. Integrations and agent people pair on any in-flow Jev decision, where most bugs will be.
- **Done =** merged, tests pass, works against fixtures, and shown at sync if user-facing.

## Milestones (~6 weeks, ending ~2nd week of December; compress if deadline is earlier)

- **Week 1 – Foundations:** repo, CI, v1 schemas in both codebases; side panel calls deployed backend; one real Jev decision; scrubbed fixtures for all four sites; login detection on MyUHS and PrairieTest; UW's CBTF system confirmed.
- **Week 2 – Courses end to end:** chat → route → extract → ready → public API search → rank → cards; seat watcher notifies; routing eval set v1 (~50 labeled messages).
- **Week 3 – Harness + first logged-in flow:** snapshot, executor, loop runner done; PrairieTest search returns real slots; confirm gate works end to end, commit impossible without token.
- **Week 4 – Booking:** CBTF booking with verification; UHS search/booking for one appointment type plus `handed_off`; tickets watcher alerts.
- **Week 5 – Tuning:** calendar conflicts and preferences feed ranking; thresholds tuned from evals; proper UI error states and retries.
- **Week 6 – Demo:** bug bash and real-world trial on the team's own accounts; demo script, writeup, slides.

## Testing and evals

- Adapters get unit tests against saved fixtures (load HTML, run search and book up to the confirm click). Live-site testing is manual and occasional to avoid hammering UW systems.
- P5's four labeled sets: routing messages, readiness cases, page states (from fixtures), commit vs non-commit actions.
- For each, track accuracy and calibration (does high confidence mean correct?), then set thresholds. `is_commit` must never miss a real commit on the eval set, even at the cost of extra confirmations.

## Security, privacy, and policy

- Never collect NetID passwords; users sign in themselves and always do Duo.
- Jev and LLM keys live only on the backend.
- Snapshots are stripped to interactive elements and short text, with redaction, before leaving the browser. UHS snapshots never stored; UHS decisions logged without page content.
- `host_permissions` lists only the four sites and our backend.
- Every commit needs explicit user confirmation; no model can override this.
- Watchers use minimum polling intervals, backoff, and caching.
- Before demoing on real accounts, check UW's IT acceptable use policy and each site's terms. Stay assistive: users confirm every action, and watchers alert rather than grab scarce slots/tickets faster than humans.

## Risks and open questions

- **UW's CBTF system:** unconfirmed; Charlie (P6) checks week 1.
- **Jev is early access:** rate limits/API may change; wrapper's LLM fallback covers outages.
- **Site HTML changes:** fixtures catch breaks in CI; `next_action` provides a fallback meanwhile.
- **Duo sessions expiring mid-flow:** every step checks `page_state` and drops cleanly to `login_required`.
- **MV3 service worker suspension:** long flows run while side panel is open; background checks stay short.
- **Real deadline:** milestones assume six weeks.
- **iPhone support:** later, consider a Safari web extension conversion.

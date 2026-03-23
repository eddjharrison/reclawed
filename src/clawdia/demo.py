"""Demo data generator for screenshot capture.

Creates a pre-populated database showcasing all features:
workspaces, solo chats, group chats, orchestrator/workers,
tool activity, questions, choices, @mentions, bookmarks, etc.

Usage: clawdia --demo
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clawdia.config import Config, Workspace
from clawdia.models import Message, Session
from clawdia.store import Store


def _id() -> str:
    return str(uuid.uuid4())


def _ts(minutes_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


def create_demo_data() -> tuple[Config, Path]:
    """Create a temp directory with a fully-populated demo database.

    Returns (config, db_path) ready to pass to ClawdiaApp.
    """
    data_dir = Path(tempfile.mkdtemp(prefix="clawdia-demo-"))
    db_path = data_dir / "history.db"

    config = Config(
        data_dir=data_dir,
        theme="dark",
        participant_name="Ed",
        permission_mode="acceptEdits",
        auto_name_sessions=False,
        workspaces=[
            Workspace(name="Frontend", path="~/projects/frontend", color="cyan"),
            Workspace(name="Backend API", path="~/projects/backend", color="yellow"),
            Workspace(name="Mobile App", path="~/projects/mobile-app", color="green"),
        ],
    )

    store = Store(db_path)  # no encryption for demo

    # --- IDs for cross-referencing ---
    orch_id = _id()
    worker1_id = _id()
    worker2_id = _id()
    worker3_id = _id()
    bookmark_msg_id = _id()
    reply_target_id = _id()

    # =====================================================================
    # 1. "Refactor auth middleware" — Backend, pinned, rich content
    # =====================================================================
    s1_id = _id()
    s1 = Session(
        id=s1_id, name="Refactor auth middleware",
        created_at=_ts(180), updated_at=_ts(5),
        model="sonnet", cwd="~/projects/backend",
        total_cost_usd=0.47, message_count=8,
        pinned=True, permission_mode="acceptEdits",
        last_input_tokens=45000,
    )
    store.create_session(s1)

    _add(store, s1_id, "user", "The auth middleware is checking JWT tokens on every request even for public routes. Can you refactor it to skip auth for routes marked as public?", 180, sender_name="Ed")

    _add(store, s1_id, "assistant", """I'll look at the current middleware structure first.

**Reading** `src/middleware/auth.py`...

The issue is clear — `authenticate()` runs unconditionally in the middleware chain. Here's my plan:

1. Add a `public_routes` set to the config
2. Create a `skip_auth` decorator for route handlers
3. Modify the middleware to check the route before validating tokens

```python
PUBLIC_ROUTES = {"/health", "/login", "/register", "/docs"}

class AuthMiddleware:
    async def __call__(self, request, call_next):
        if request.url.path in PUBLIC_ROUTES:
            return await call_next(request)
        token = request.headers.get("Authorization")
        if not token:
            return JSONResponse(status_code=401, content={"error": "Missing token"})
        # ... validate token ...
```

**Should I also add rate limiting to the public routes, or keep this focused on the auth bypass?**""",
        175, model="sonnet", cost=0.12, input_tokens=12000, output_tokens=850, duration=3200,
        sender_name="Claude")

    _add(store, s1_id, "user", "Keep it focused on auth only. Go ahead and implement it.", 170, sender_name="Ed")

    _add(store, s1_id, "assistant", """**Editing** `src/middleware/auth.py`...
**Editing** `src/config/routes.py`...
**Running** `pytest tests/test_auth.py -v`...

Done. Here's what changed:

- Added `PUBLIC_ROUTES` config in `src/config/routes.py`
- Modified `AuthMiddleware.__call__()` to skip token validation for public paths
- Added `@public` decorator that auto-registers routes

```python
@public
@router.get("/health")
async def health():
    return {"status": "ok"}
```

All 23 auth tests pass. The `/health` endpoint now responds in **2ms** instead of **45ms** (no JWT decode).

Do you want me to:
1. Add tests specifically for the public route bypass
2. Update the API documentation
3. Add a warning log when an unknown route is accessed without auth""",
        165, model="sonnet", cost=0.15, input_tokens=18000, output_tokens=1200, duration=8500,
        sender_name="Claude", msg_id=bookmark_msg_id, bookmarked=True)

    _add(store, s1_id, "user", "Option 1 — add the tests.", 160, sender_name="Ed")

    _add(store, s1_id, "assistant", """**Writing** `tests/test_public_routes.py`...
**Running** `pytest tests/test_public_routes.py -v`...

```
tests/test_public_routes.py::test_health_no_auth      PASSED
tests/test_public_routes.py::test_login_no_auth        PASSED
tests/test_public_routes.py::test_register_no_auth     PASSED
tests/test_public_routes.py::test_private_requires_auth PASSED
tests/test_public_routes.py::test_unknown_route_401    PASSED
```

All 5 new tests pass. Total suite: **28 tests, 0 failures**.""",
        155, model="sonnet", cost=0.08, input_tokens=22000, output_tokens=600, duration=5100,
        sender_name="Claude")

    _add(store, s1_id, "user", "Perfect. Can you also check if there are any middleware ordering issues?", 140, sender_name="Ed", msg_id=reply_target_id)

    _add(store, s1_id, "assistant", """**Reading** `src/app.py` (middleware stack)...
**Reading** `src/middleware/__init__.py`...

The middleware ordering looks correct:

```
1. CORSMiddleware        (outermost — handles preflight)
2. AuthMiddleware         (auth check — now skips public routes)
3. RateLimitMiddleware    (rate limiting)
4. RequestLogMiddleware   (innermost — logging)
```

No issues. Auth runs before rate limiting, which is right — you don't want to rate-limit unauthenticated requests that will be rejected anyway. The CORS middleware needs to be outermost for preflight `OPTIONS` requests.""",
        135, model="sonnet", cost=0.10, input_tokens=28000, output_tokens=400, duration=2800,
        sender_name="Claude", reply_to=reply_target_id)

    _add(store, s1_id, "user", "Great work, thanks!", 130, sender_name="Ed")

    # =====================================================================
    # 2. "Fix CSS grid layout" — Frontend, edited message, opus
    # =====================================================================
    s2_id = _id()
    s2 = Session(
        id=s2_id, name="Fix CSS grid layout",
        created_at=_ts(120), updated_at=_ts(60),
        model="opus", cwd="~/projects/frontend",
        total_cost_usd=0.83, message_count=4,
        last_input_tokens=32000,
    )
    store.create_session(s2)

    _add(store, s2_id, "user", "The dashboard grid breaks on tablet screens (768-1024px). Cards overlap and the sidebar disappears.", 120, sender_name="Ed")

    _add(store, s2_id, "assistant", """**Reading** `src/components/Dashboard.tsx`...
**Reading** `src/styles/grid.css`...

Found it. The grid template is using fixed `240px` for the sidebar, which doesn't leave enough room on tablets. The cards use `grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))` which creates overlap when the container shrinks.

```css
/* Before */
.dashboard {
    grid-template-columns: 240px 1fr;
}

/* After — responsive sidebar with clamp */
.dashboard {
    grid-template-columns: clamp(180px, 20vw, 240px) 1fr;
}

@media (max-width: 768px) {
    .dashboard {
        grid-template-columns: 1fr;
    }
    .sidebar {
        position: fixed;
        transform: translateX(-100%);
    }
}
```

**Editing** `src/styles/grid.css`...

The cards also need a smaller `minmax`:
```css
.card-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}
```""",
        115, model="opus", cost=0.42, input_tokens=15000, output_tokens=900, duration=4500,
        sender_name="Claude")

    _add(store, s2_id, "user", "Actually, can you use a container query instead of the media query? We're using modern browsers only.", 108,
         sender_name="Ed", edited_at=_ts(105))

    _add(store, s2_id, "assistant", """Good call — container queries are cleaner here since the dashboard can be embedded at different widths.

**Editing** `src/styles/grid.css`...

```css
.dashboard-wrapper {
    container-type: inline-size;
}

.dashboard {
    grid-template-columns: clamp(180px, 20cqi, 240px) 1fr;
}

@container (max-width: 768px) {
    .dashboard {
        grid-template-columns: 1fr;
    }
}
```

**Running** `npm run test:visual`...

Visual regression tests pass. The grid now responds to its container width, not the viewport. This means it works correctly whether the dashboard is full-page or embedded in a panel.""",
        100, model="opus", cost=0.38, input_tokens=20000, output_tokens=700, duration=3800,
        sender_name="Claude")

    # =====================================================================
    # 3. "Debug API timeout" — Backend, bypassPermissions
    # =====================================================================
    s3_id = _id()
    s3 = Session(
        id=s3_id, name="Debug API timeout",
        created_at=_ts(90), updated_at=_ts(45),
        model="sonnet", cwd="~/projects/backend",
        total_cost_usd=0.22, message_count=4,
        permission_mode="bypassPermissions",
        last_input_tokens=55000,
    )
    store.create_session(s3)

    _add(store, s3_id, "user", "The /api/reports endpoint is timing out after 30s for large datasets. Can you profile it and fix it?", 90, sender_name="Ed")

    _add(store, s3_id, "assistant", """**Reading** `src/routes/reports.py`...
**Running** `python -m cProfile -o profile.out scripts/test_reports.py`...
**Reading** profile output...

Found the bottleneck. The `generate_report()` function loads **all records into memory** before filtering:

```
   ncalls  tottime  cumtime  filename:lineno(function)
   1       12.450   12.450  reports.py:45(generate_report)
   50000    8.200    8.200  reports.py:78(_format_row)
   1        3.100    3.100  reports.py:92(_serialize)
```

12.4s on `generate_report` alone — it's fetching 50K rows then filtering in Python. This should be a database query with `LIMIT`/`OFFSET` and server-side filtering.

**Editing** `src/routes/reports.py`...
**Editing** `src/db/queries.py`...
**Running** `pytest tests/test_reports.py -v`...

Refactored to use pagination and DB-side filtering. The endpoint now streams results:

| Dataset | Before | After |
|---------|--------|-------|
| 1K rows | 2.1s | 0.08s |
| 10K rows | 8.5s | 0.12s |
| 50K rows | 32s (timeout) | 0.15s |""",
        85, model="sonnet", cost=0.15, input_tokens=30000, output_tokens=1100, duration=12000,
        sender_name="Claude")

    _add(store, s3_id, "user", "That's a huge improvement. Does the pagination work with the existing frontend?", 75, sender_name="Ed")

    _add(store, s3_id, "assistant", """**Reading** `frontend/src/hooks/useReports.ts`...

The frontend already handles paginated responses — it uses `react-query` with `useInfiniteQuery`. The API change is backward-compatible because:

1. The response still has `data[]` and `total` fields
2. New `next_cursor` field is optional — old clients ignore it
3. Default page size (100) matches what the frontend was expecting

No frontend changes needed.""",
        70, model="sonnet", cost=0.07, input_tokens=35000, output_tokens=300, duration=1800,
        sender_name="Claude")

    # =====================================================================
    # 4. "Setup CI pipeline" — Mobile, shorter
    # =====================================================================
    s4_id = _id()
    s4 = Session(
        id=s4_id, name="Setup CI pipeline",
        created_at=_ts(60), updated_at=_ts(50),
        model="sonnet", cwd="~/projects/mobile-app",
        total_cost_usd=0.09, message_count=2,
        last_input_tokens=8000,
    )
    store.create_session(s4)

    _add(store, s4_id, "user", "Can you set up a GitHub Actions workflow for the mobile app? Build, lint, test on push to main and PRs.", 60, sender_name="Ed")

    _add(store, s4_id, "assistant", """**Writing** `.github/workflows/ci.yml`...

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npm run lint
      - run: npm test -- --coverage
      - run: npm run build
```

This covers lint, test with coverage, and build. Push to main and PR triggers. Want me to add caching for `node_modules` or a separate deploy step?""",
        55, model="sonnet", cost=0.05, input_tokens=5000, output_tokens=400, duration=2100,
        sender_name="Claude")

    # =====================================================================
    # 5. "Sprint planning" — Group chat, Backend
    # =====================================================================
    s5_id = _id()
    s5 = Session(
        id=s5_id, name="Sprint planning",
        created_at=_ts(200), updated_at=_ts(10),
        model="sonnet", cwd="~/projects/backend",
        is_group=True, room_mode="claude_assists",
        relay_url="ws://127.0.0.1:8765",
        room_id=_id(), participant_id=_id(),
        relay_token="demo-token",
        total_cost_usd=0.31, message_count=8,
        unread_count=2,
        last_input_tokens=20000,
    )
    store.create_session(s5)

    _add(store, s5_id, "user", "Hey Alice, ready to plan the sprint? I've got the auth refactor done, what's left on your end?", 200,
         sender_name="Ed", sender_type="human")

    _add(store, s5_id, "user", "Yeah! I finished the payment integration yesterday. Still need to wire up webhooks and add retry logic.", 195,
         sender_name="Alice", sender_type="human")

    _add(store, s5_id, "user", "@Ed's Claude can you check what tests are failing in the payment module?", 190,
         sender_name="Alice", sender_type="human")

    _add(store, s5_id, "assistant", """**Running** `pytest tests/test_payments.py -v`...

3 tests failing:

```
FAILED test_webhook_signature_validation - AssertionError: expected 200, got 401
FAILED test_retry_on_timeout - TimeoutError: payment gateway unreachable
FAILED test_idempotency_key - duplicate charge created
```

The webhook signature test is failing because the secret key changed after the integration update. The other two are real bugs — the retry logic isn't implemented yet and there's no idempotency check.""",
        185, model="sonnet", cost=0.08, input_tokens=10000, output_tokens=500, duration=4200,
         sender_name="Ed's Claude", sender_type="claude")

    _add(store, s5_id, "user", "Thanks! I'll take the webhook fix. @Alice can you handle the idempotency key?", 180,
         sender_name="Ed", sender_type="human")

    _add(store, s5_id, "user", "On it. I'll add a request_id column to the charges table. @Alice's Claude can you draft the migration?", 175,
         sender_name="Alice", sender_type="human")

    _add(store, s5_id, "assistant", """Here's the migration:

```sql
ALTER TABLE charges ADD COLUMN idempotency_key TEXT UNIQUE;
CREATE INDEX idx_charges_idempotency ON charges(idempotency_key);
```

And the check in the handler:

```python
existing = await db.charges.find_one(idempotency_key=request.idempotency_key)
if existing:
    return existing  # return cached result, don't create duplicate
```

This ensures each payment request is processed exactly once, even if the client retries.""",
        170, model="sonnet", cost=0.06, input_tokens=12000, output_tokens=400, duration=2800,
         sender_name="Alice's Claude", sender_type="claude")

    _add(store, s5_id, "user", "Perfect. Let's target Wednesday for all three fixes. I'll create the tickets.", 165,
         sender_name="Ed", sender_type="human")

    # =====================================================================
    # 6. "Pair debugging" — Group chat, Frontend
    # =====================================================================
    s6_id = _id()
    s6 = Session(
        id=s6_id, name="Pair debugging session",
        created_at=_ts(150), updated_at=_ts(30),
        model="sonnet", cwd="~/projects/frontend",
        is_group=True, room_mode="full_auto",
        relay_url="ws://127.0.0.1:8765",
        room_id=_id(), participant_id=_id(),
        relay_token="demo-token-2",
        total_cost_usd=0.18, message_count=4,
        last_input_tokens=15000,
    )
    store.create_session(s6)

    _add(store, s6_id, "user", "The WebSocket connection keeps dropping after exactly 60 seconds. Is there a timeout somewhere?", 150,
         sender_name="Ed", sender_type="human")

    _add(store, s6_id, "user", "I've seen this before — check if your reverse proxy has an idle timeout. Nginx defaults to 60s for WebSocket.", 145,
         sender_name="Marcus", sender_type="human")

    _add(store, s6_id, "assistant", """Marcus is right. **Reading** `nginx/conf.d/websocket.conf`...

```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    # Missing: proxy_read_timeout
}
```

No `proxy_read_timeout` set — Nginx defaults to **60 seconds**. Add:

```nginx
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

Also add a ping/pong keepalive on the application side (every 30s) so the connection stays active even with no traffic.""",
        140, model="sonnet", cost=0.10, input_tokens=8000, output_tokens=500, duration=3200,
         sender_name="Ed's Claude", sender_type="claude")

    _add(store, s6_id, "user", "That was it! Connection stays up now. Thanks both.", 130,
         sender_name="Ed", sender_type="human")

    # =====================================================================
    # 7. "Deploy v2.0" — Orchestrator
    # =====================================================================
    orch = Session(
        id=orch_id, name="Deploy v2.0",
        created_at=_ts(240), updated_at=_ts(15),
        model="opus", cwd="~/projects/backend",
        session_type="orchestrator",
        total_cost_usd=1.24, message_count=4,
        permission_mode="acceptEdits",
        last_input_tokens=60000,
    )
    store.create_session(orch)

    _add(store, orch_id, "user", "We need to deploy v2.0. There are migration scripts, updated API docs, and the new auth system. Can you orchestrate this?", 240, sender_name="Ed")

    _add(store, orch_id, "assistant", """I'll break this into parallel tasks:

{{WORKER task="Run database migrations and verify schema changes" model="sonnet" permissions="bypassPermissions" template="implementation"}}

{{WORKER task="Generate updated API documentation from OpenAPI spec" model="sonnet" permissions="acceptEdits" template="doc-writer"}}

{{WORKER task="Review the new auth middleware for security issues" model="opus" permissions="default" template="code-reviewer"}}

I'll coordinate the results once all three complete. The migration must succeed before we can proceed with deployment.""",
        235, model="opus", cost=0.52, input_tokens=25000, output_tokens=600, duration=4800,
        sender_name="Claude")

    _add(store, orch_id, "assistant", """Workers i1 and i2 have completed.

**i1 (Migrations):** All 3 migrations applied successfully. Schema verified — new `idempotency_key` column on charges, updated indexes, session token table created.

**i2 (API Docs):** OpenAPI spec updated with 12 new endpoints, 3 deprecated. Generated HTML docs at `docs/api/v2/`.

Waiting on **i3 (Security Review)** before proceeding with deployment.""",
        25, model="opus", cost=0.35, input_tokens=45000, output_tokens=400, duration=3500,
        sender_name="Claude")

    _add(store, orch_id, "user", "Good. Let me know as soon as the security review is done.", 20, sender_name="Ed")

    # =====================================================================
    # 8-10. Worker sessions
    # =====================================================================
    w1 = Session(
        id=worker1_id, name="Run database migrations",
        created_at=_ts(230), updated_at=_ts(40),
        model="sonnet", cwd="~/projects/backend",
        session_type="worker", parent_session_id=orch_id,
        worker_status="complete",
        worker_summary="Applied 3 migrations successfully: added idempotency_key column, created session_tokens table, updated indexes. Schema verified against ORM models.",
        worker_template_id="implementation",
        permission_mode="bypassPermissions",
        total_cost_usd=0.18, message_count=2,
        last_input_tokens=30000,
    )
    store.create_session(w1)

    _add(store, worker1_id, "assistant", """**Running** `alembic upgrade head`...

```
INFO  [alembic.runtime.migration] Running upgrade 3a2f -> 4b1c, Add idempotency_key
INFO  [alembic.runtime.migration] Running upgrade 4b1c -> 5d2e, Create session_tokens
INFO  [alembic.runtime.migration] Running upgrade 5d2e -> 6f3g, Update payment indexes
```

All 3 migrations applied. Verifying schema...

**Running** `python scripts/verify_schema.py`...

Schema matches ORM models. No drift detected.""",
        225, model="sonnet", cost=0.12, input_tokens=15000, output_tokens=400, duration=8000,
        sender_name="Claude")

    w2 = Session(
        id=worker2_id, name="Generate API documentation",
        created_at=_ts(230), updated_at=_ts(35),
        model="sonnet", cwd="~/projects/backend",
        session_type="worker", parent_session_id=orch_id,
        worker_status="complete",
        worker_summary="Updated OpenAPI spec with 12 new endpoints and 3 deprecations. Generated HTML docs. All examples validated against live schema.",
        worker_template_id="doc-writer",
        permission_mode="acceptEdits",
        total_cost_usd=0.14, message_count=2,
        last_input_tokens=25000,
    )
    store.create_session(w2)

    _add(store, worker2_id, "assistant", """**Reading** `src/routes/*.py` (scanning decorators)...
**Writing** `docs/openapi/v2.yaml`...
**Running** `npx redoc-cli build docs/openapi/v2.yaml -o docs/api/v2/index.html`...

Generated documentation for v2.0:
- **12 new endpoints** (payments, webhooks, session management)
- **3 deprecated** (legacy auth, old report format, v1 health)
- All request/response examples validated against JSON schemas""",
        220, model="sonnet", cost=0.10, input_tokens=18000, output_tokens=500, duration=6000,
        sender_name="Claude")

    w3 = Session(
        id=worker3_id, name="Security review: auth middleware",
        created_at=_ts(230), updated_at=_ts(15),
        model="opus", cwd="~/projects/backend",
        session_type="worker", parent_session_id=orch_id,
        worker_status="running",
        worker_template_id="code-reviewer",
        permission_mode="default",
        total_cost_usd=0.22, message_count=1,
        last_input_tokens=40000,
    )
    store.create_session(w3)

    _add(store, worker3_id, "assistant", """**Reading** `src/middleware/auth.py`...
**Reading** `src/utils/jwt.py`...
**Reading** `src/config/security.py`...

Reviewing auth middleware for OWASP Top 10 vulnerabilities...

**Findings so far:**

- Token expiry check is correct (exp claim validated)
- HMAC signature uses HS256 — consider upgrading to RS256 for production
- `PUBLIC_ROUTES` set is hardcoded — should be loaded from config to prevent drift
- Missing: rate limiting on `/login` endpoint (brute force risk)

Still reviewing the session management and CSRF protection...""",
        20, model="opus", cost=0.22, input_tokens=40000, output_tokens=600, duration=5500,
        sender_name="Claude")

    store.close()
    return config, db_path


def _add(
    store: Store,
    session_id: str,
    role: str,
    content: str,
    minutes_ago: int,
    *,
    model: str | None = None,
    cost: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration: int | None = None,
    sender_name: str | None = None,
    sender_type: str | None = None,
    msg_id: str | None = None,
    bookmarked: bool = False,
    reply_to: str | None = None,
    edited_at: datetime | None = None,
) -> str:
    """Helper to add a message with less boilerplate."""
    mid = msg_id or _id()
    msg = Message(
        id=mid,
        role=role,
        content=content,
        session_id=session_id,
        seq=0,  # auto-assigned by store
        timestamp=_ts(minutes_ago),
        model=model,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration,
        sender_name=sender_name,
        sender_type=sender_type,
        bookmarked=bookmarked,
        reply_to_id=reply_to,
        edited_at=edited_at,
    )
    store.add_message(msg)
    return mid

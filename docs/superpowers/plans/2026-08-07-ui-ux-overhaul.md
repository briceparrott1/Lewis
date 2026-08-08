# UI/UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix navigation dead-ends, make Lewis speak first and acknowledge what users actually say, persist job preferences across conversations, apply a deliberate chat-first visual theme, and stream LLM text as it's generated.

**Architecture:** Four sequential phases (Nav → Agent behavior/prefs → Theme → Streaming), each independently shippable. No DB migration needed anywhere — `UserProfile.structured_prefs` already exists as a column, it's just never been wired up.

**Tech Stack:** FastAPI + LangGraph + SQLAlchemy (async) + Anthropic SDK 0.120 on the backend; React + Vite + TS + Tailwind v4 + TanStack Query + React Router v6 on the frontend. `uv` for Python, `pnpm` for web.

## Global Constraints

- Backend: PEP 8 compliant; format with Black (88 cols); imports sorted by Ruff. `cd apps/api && uv run ruff check .` and `uv run black --check .` must pass on every task.
- Backend tests: `cd apps/api && uv run pytest -q` (auto-creates the `lewis_test` DB).
- Frontend: `cd apps/web && pnpm typecheck` and `pnpm test` must pass on every task. No new dependency (icon library, component library, animation library) — stay CSS/plain-React.
- No new DB migration — `structured_prefs` (JSONB) already exists on `user_profiles`.
- No dedicated preferences/settings page — preferences are viewed/changed conversationally only.
- Cost-conscious LLM usage: default model stays whatever `settings.agent_model` already is (Haiku); the client-rendered greeting (Phase 2) makes no LLM call at all.
- No unused imports left behind after edits — every file this plan touches that loses a usage (e.g. a removed `<Link>`) must have its import cleaned up too.

---

# Phase 1 — Navigation & app shell

## Task 1: `useAuth` gains a `logout()` method

**Files:**
- Modify: `apps/web/src/auth.tsx`
- Test: `apps/web/src/auth.test.tsx`

**Interfaces:**
- Produces: `useAuth().logout(): Promise<void>` — POSTs `/auth/logout`, then invalidates the `["me"]` query so `user` becomes `null` on next render. Consumed by Task 2's `AppLayout`.

- [ ] **Step 1: Write the failing test**

Add to `apps/web/src/auth.test.tsx` (new `describe` block, keep the existing `Login` block as-is):

```tsx
import { useAuth, AuthProvider } from "./auth";

function Probe() {
  const { logout } = useAuth();
  return <button onClick={() => logout()}>do logout</button>;
}

describe("useAuth logout", () => {
  it("posts to /auth/logout and invalidates the me query", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/auth/logout")
        return new Response("{}", { headers: { "content-type": "application/json" } });
      return new Response("null", { headers: { "content-type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    wrap(<Probe />);
    await userEvent.click(screen.getByRole("button", { name: /do logout/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/auth/logout",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- auth.test.tsx`
Expected: FAIL — `logout` is `undefined` on the context value, `TypeError: logout is not a function`.

- [ ] **Step 3: Implement `logout()`**

Replace the full contents of `apps/web/src/auth.tsx`:

```tsx
import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { User } from "./types";

async function fetchMe(): Promise<User | null> {
  try {
    return (await api.get("/auth/me")) as User;
  } catch {
    return null;
  }
}

interface AuthValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthValue>({
  user: null,
  loading: true,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  return (
    <Ctx.Provider
      value={{
        user: data ?? null,
        loading: isLoading,
        refresh: () => qc.invalidateQueries({ queryKey: ["me"] }),
        logout: async () => {
          await api.post("/auth/logout");
          await qc.invalidateQueries({ queryKey: ["me"] });
        },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- auth.test.tsx`
Expected: PASS (both the new logout test and the existing Login test).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/auth.tsx apps/web/src/auth.test.tsx
git commit -m "feat: add logout() to useAuth"
```

---

## Task 2: `AppLayout` shared header

**Files:**
- Create: `apps/web/src/components/AppLayout.tsx`
- Create: `apps/web/src/components/AppLayout.test.tsx`

**Interfaces:**
- Consumes: `useAuth().logout()` (Task 1).
- Produces: `AppLayout` component — renders a header (wordmark, Chat/Saved/Profile nav links, Logout) above a react-router `<Outlet />`. Consumed by Task 3's routing.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/AppLayout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import { AppLayout } from "./AppLayout";

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<div>chat page</div>} />
              <Route path="/login" element={<div>login page</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppLayout", () => {
  it("renders nav links to Chat, Saved, and Profile", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("null", { headers: { "content-type": "application/json" } })),
    );
    renderLayout();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Saved" })).toHaveAttribute("href", "/saved");
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/onboarding");
    vi.unstubAllGlobals();
  });

  it("logs out and navigates to /login on Logout click", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/auth/logout")
        return new Response("{}", { headers: { "content-type": "application/json" } });
      return new Response("null", { headers: { "content-type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderLayout();
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST" }),
    );
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- AppLayout.test.tsx`
Expected: FAIL — `Failed to resolve import "./AppLayout"`.

- [ ] **Step 3: Implement `AppLayout`**

Create `apps/web/src/components/AppLayout.tsx`:

```tsx
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function AppLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "font-medium text-black" : "text-gray-600 hover:text-black";

  return (
    <div className="min-h-screen">
      <header className="border-b px-6 py-3">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <NavLink to="/" className="font-semibold">Lewis</NavLink>
          <nav className="flex items-center gap-4 text-sm">
            <NavLink to="/" end className={linkClass}>Chat</NavLink>
            <NavLink to="/saved" className={linkClass}>Saved</NavLink>
            <NavLink to="/onboarding" className={linkClass}>Profile</NavLink>
            <button type="button" onClick={handleLogout} className="text-gray-600 hover:text-black">
              Logout
            </button>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- AppLayout.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/AppLayout.tsx apps/web/src/components/AppLayout.test.tsx
git commit -m "feat: add shared AppLayout header with nav and logout"
```

---

## Task 3: Wire `AppLayout` into routing, remove duplicate nav links

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/pages/Chat.tsx` (remove duplicate "Saved jobs" link)
- Modify: `apps/web/src/pages/Saved.tsx` (remove duplicate "Back to search" link)
- Create: `apps/web/src/App.test.tsx`

**Interfaces:**
- Consumes: `AppLayout` (Task 2), existing `RequireAuth`/`RequireResume` guards (unchanged).

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { App } from "./App";

function renderApp(path: string, profileOverrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me")
      return new Response(JSON.stringify({ id: "u1", email: "a@b.com" }), {
        headers: { "content-type": "application/json" },
      });
    if (url === "/api/profile")
      return new Response(
        JSON.stringify({
          name: null,
          resume_text: "resume",
          raw_prefs_text: null,
          structured_prefs: {},
          ...profileOverrides,
        }),
        { headers: { "content-type": "application/json" } },
      );
    return new Response("null", { headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App routing", () => {
  it("shows the shared header nav when visiting onboarding while authenticated", async () => {
    renderApp("/onboarding");
    expect(await screen.findByText("Upload your resume")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("redirects an authenticated user with no resume from / to onboarding", async () => {
    renderApp("/", { resume_text: null });
    expect(await screen.findByText("Upload your resume")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- App.test.tsx`
Expected: FAIL — no shared header exists yet, so `getByRole("link", { name: "Chat" })` throws.

- [ ] **Step 3: Wire the layout route**

Replace the full contents of `apps/web/src/App.tsx`:

```tsx
import { Routes, Route, Navigate } from "react-router-dom";
import { RequireAuth } from "./components/RequireAuth";
import { RequireResume } from "./components/RequireResume";
import { AppLayout } from "./components/AppLayout";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { Onboarding } from "./pages/Onboarding";
import { Chat } from "./pages/Chat";
import { Saved } from "./pages/Saved";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/onboarding" element={<Onboarding />} />
        <Route
          path="/"
          element={
            <RequireResume>
              <Chat />
            </RequireResume>
          }
        />
        <Route path="/saved" element={<Saved />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 4: Remove the duplicate "Saved jobs" link from Chat's toolbar**

In `apps/web/src/pages/Chat.tsx`, remove the now-unused `Link` import (`import { Link } from "react-router-dom";`) and replace the header row:

```tsx
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Find roles</h1>
        <div className="flex gap-3 text-sm">
          <Link className="text-blue-600" to="/saved">Saved jobs</Link>
          <button className="text-gray-600" onClick={newChat}>New chat</button>
        </div>
      </div>
```

with:

```tsx
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Find roles</h1>
        <button className="text-sm text-gray-600" onClick={newChat}>New chat</button>
      </div>
```

- [ ] **Step 5: Remove the duplicate "Back to search" link from Saved**

Replace the full contents of `apps/web/src/pages/Saved.tsx`:

```tsx
import { JobCard } from "../components/JobCard";
import { useJobs, useUnsaveJob } from "../queries";

export function Saved() {
  const { data, isLoading } = useJobs();
  const unsave = useUnsaveJob();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Saved jobs</h1>
      </div>
      {isLoading && <p>Loading…</p>}
      {data && data.length === 0 && <p className="text-gray-600">No saved jobs yet.</p>}
      {data?.map((job) => (
        <JobCard
          key={job.id}
          job={job}
          action="unsave"
          busy={unsave.isPending}
          onAction={() => unsave.mutate(job.id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Run the full frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — App.test.tsx passes, and Chat.test.tsx / Saved.test.tsx still pass unchanged (neither asserted on the removed links).

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/pages/Chat.tsx apps/web/src/pages/Saved.tsx
git commit -m "feat: wire AppLayout into routing, dedupe nav links"
```

---

# Phase 2 — Agent behavior & persistent preferences

## Task 4: `missing_fields` helper in `prefs.py`

**Files:**
- Modify: `apps/api/lewis_api/agent/prefs.py`
- Test: `apps/api/tests/agent/test_prefs.py`

**Interfaces:**
- Produces: `missing_fields(prefs: StructuredPrefs) -> list[str]`. Consumed by Task 5's `clarify.py`.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/agent/test_prefs.py` (update the import line at top to `from lewis_api.agent.prefs import is_sufficient, missing_fields, parse_prefs`):

```python
def test_missing_fields_lists_gaps():
    assert missing_fields({}) == ["role", "location or remote work", "seniority level"]
    assert missing_fields({"role_keywords": ["fde"]}) == [
        "location or remote work",
        "seniority level",
    ]
    assert missing_fields(
        {"role_keywords": ["fde"], "locations": ["SF"], "seniority": "mid"}
    ) == []
    assert missing_fields({"role_keywords": ["fde"], "remote_ok": True}) == [
        "seniority level"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_prefs.py -v`
Expected: FAIL — `ImportError: cannot import name 'missing_fields'`.

- [ ] **Step 3: Implement `missing_fields`**

Add to `apps/api/lewis_api/agent/prefs.py`, after `is_sufficient`:

```python
def missing_fields(prefs: StructuredPrefs) -> list[str]:
    """Human-readable list of preference gaps to ask about. Role and
    location/remote gate whether the graph can search (see is_sufficient);
    seniority is included too since Lewis always asks for it, even though it
    isn't gating."""
    missing = []
    if not prefs.get("role_keywords"):
        missing.append("role")
    if not prefs.get("locations") and prefs.get("remote_ok") is not True:
        missing.append("location or remote work")
    if not prefs.get("seniority"):
        missing.append("seniority level")
    return missing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/agent/test_prefs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/prefs.py apps/api/tests/agent/test_prefs.py
git commit -m "feat: add missing_fields helper for clarify prompts"
```

---

## Task 5: Natural clarify replies (`clarify.py`)

**Files:**
- Create: `apps/api/lewis_api/agent/clarify.py`
- Create: `apps/api/tests/agent/test_clarify.py`

**Interfaces:**
- Consumes: `missing_fields` (Task 4), `LLM.complete()` (existing).
- Produces: `generate_clarify_reply(user_message: str, prefs: StructuredPrefs, llm: LLM) -> str`, `CLARIFY_TEXT: str` (fallback constant). Consumed by Task 6's `graph.py`. **Note:** this task's non-streaming version ships in Phase 2; Task 13 (Phase 4) replaces it with a streaming variant — this is intentional, not churn to avoid (see the design doc's phase sequencing rationale).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/agent/test_clarify.py`:

```python
import pytest

from lewis_api.agent.clarify import CLARIFY_TEXT, generate_clarify_reply


class FakeLLM:
    def __init__(self, text=None, raise_exc=None):
        self.text = text
        self.raise_exc = raise_exc
        self.calls = []

    async def complete(self, system, user):
        self.calls.append((system, user))
        if self.raise_exc:
            raise self.raise_exc
        return self.text


@pytest.mark.asyncio
async def test_generate_clarify_reply_includes_message_and_missing_fields():
    llm = FakeLLM(text="Hey! Where are you looking, and what level?")
    out = await generate_clarify_reply("hi there", {}, llm)
    assert out == "Hey! Where are you looking, and what level?"
    _, user = llm.calls[0]
    assert "hi there" in user
    assert "role" in user
    assert "location or remote work" in user
    assert "seniority level" in user


@pytest.mark.asyncio
async def test_generate_clarify_reply_falls_back_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    out = await generate_clarify_reply("hi", {}, llm)
    assert out == CLARIFY_TEXT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_clarify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lewis_api.agent.clarify'`.

- [ ] **Step 3: Implement `clarify.py`**

Create `apps/api/lewis_api/agent/clarify.py`:

```python
from lewis_api.agent.llm import LLM
from lewis_api.agent.prefs import missing_fields
from lewis_api.agent.state import StructuredPrefs

CLARIFY_TEXT = (
    "To narrow this down: which locations are you targeting, or is remote OK? "
    "And what seniority (e.g. new grad, mid, senior)?"
)

_SYSTEM = (
    "You are Lewis, a friendly job-search assistant chatting with a user in a "
    "job-search app. They haven't given you enough to search yet. Briefly "
    "acknowledge what they just said — even if it's just a greeting or small "
    "talk unrelated to a job search — then ask a short, natural question "
    "covering what's still missing. 1-2 sentences, conversational, no bullet "
    "points, no markdown."
)


async def generate_clarify_reply(
    user_message: str, prefs: StructuredPrefs, llm: LLM
) -> str:
    missing = missing_fields(prefs)
    user = (
        f"User just said: {user_message!r}\n\n"
        f"Preferences gathered so far: {prefs}\n\n"
        f"Still need to ask about: {', '.join(missing)}"
    )
    try:
        return await llm.complete(system=_SYSTEM, user=user)
    except Exception:  # noqa: BLE001
        return CLARIFY_TEXT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/agent/test_clarify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/clarify.py apps/api/tests/agent/test_clarify.py
git commit -m "feat: generate natural clarify replies instead of static text"
```

---

## Task 6: Persist preferences across conversations

**Files:**
- Modify: `apps/api/lewis_api/agent/graph.py`
- Modify: `apps/api/lewis_api/chat/routes.py`
- Modify: `apps/api/tests/agent/test_graph.py`
- Modify: `apps/api/tests/test_chat.py`

**Interfaces:**
- Consumes: `CLARIFY_TEXT`, `generate_clarify_reply` (Task 5).
- Produces: `run_agent(..., prior_prefs: StructuredPrefs, ...)` — now requires a `prior_prefs` kwarg, and its terminal `done` event gains a `"prefs"` key with the final merged preferences. This is the contract Task 14 (Phase 4) builds on.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/agent/test_graph.py`, add `prior_prefs={}` to every existing `run_agent(...)` call (there are 5: in `test_clear_query_streams_results_and_reports_served`, both calls in `test_vague_query_asks_one_clarify_then_searches`, `test_served_jobs_excluded`, `test_respond_applies_company_diversity_cap`, `test_respond_excludes_seniority_mismatch`). For the second call in `test_vague_query_asks_one_clarify_then_searches`, thread the first call's final prefs through instead of a fresh `{}`:

```python
    first_prefs = first[-1]["prefs"]
    second = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs=first_prefs,
            served_keys=[],
            message="in SF",
            thread_id="u1:c2",
        )
    ]
```

Also add this new test at the end of the file:

```python
@pytest.mark.asyncio
async def test_done_event_reports_final_merged_prefs():
    graph, _llm = _graph(
        {"role_keywords": ["fde"], "locations": ["SF"], "required": ["role"]},
        {"rankings": []},
    )
    events = [
        e
        async for e in run_agent(
            graph,
            user_id="u1",
            resume_text="r",
            prior_prefs={"remote_ok": True},
            served_keys=[],
            message="FDE in SF",
            thread_id="u1:c6",
        )
    ]
    done = events[-1]
    assert done["type"] == "done"
    assert done["prefs"]["role_keywords"] == ["fde"]
    assert done["prefs"]["remote_ok"] is True  # prior preserved
```

In `apps/api/tests/test_chat.py`, add this new test (after the existing two):

```python
@pytest.mark.asyncio
async def test_chat_seeds_prior_prefs_from_profile_and_persists_final_prefs(
    client, monkeypatch
):
    await _signup(client, "prefs@e.com")
    captured = []

    async def fake_run_agent(*args, **kwargs):
        captured.append(kwargs["prior_prefs"])
        yield {
            "type": "done",
            "count": 0,
            "served_keys": [],
            "prefs": {"role_keywords": ["fde"]},
        }

    monkeypatch.setattr(chat_routes, "run_agent", fake_run_agent)
    app.state.agent_graph = object()

    r1 = await client.post(
        "/api/chat", json={"message": "fde jobs", "conversation_id": "c1"}
    )
    assert r1.status_code == 200
    assert captured[0] == {}  # nothing stored yet

    prof = await client.get("/api/profile")
    assert prof.json()["structured_prefs"] == {"role_keywords": ["fde"]}

    # New conversation_id (simulates "New chat") — prefs must still carry over
    r2 = await client.post(
        "/api/chat", json={"message": "anything else", "conversation_id": "c2"}
    )
    assert r2.status_code == 200
    assert captured[1] == {"role_keywords": ["fde"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py tests/test_chat.py -v`
Expected: FAIL — `run_agent() missing 1 required keyword-only argument: 'prior_prefs'`.

- [ ] **Step 3: Update `graph.py`**

In `apps/api/lewis_api/agent/graph.py`:

Replace the imports and remove the module-level `CLARIFY_TEXT`:

```python
import logging
from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.clarify import CLARIFY_TEXT, generate_clarify_reply
from lewis_api.agent.narrate import narrate_results
from lewis_api.agent.normalize import job_key
from lewis_api.agent.prefilter import prefilter
from lewis_api.agent.prefs import is_sufficient, parse_prefs
from lewis_api.agent.rank import rank_jobs
from lewis_api.agent.select_results import select_results
from lewis_api.agent.seniority import filter_by_seniority
from lewis_api.agent.state import AgentState, StructuredPrefs
from lewis_api.agent.tracing import langfuse_run_config
from lewis_api.config import get_settings

logger = logging.getLogger(__name__)


def build_graph(llm, fetch_boards, seed, checkpointer):
```

(i.e. delete the old `CLARIFY_TEXT = (...)` block that sat between the logger line and `def build_graph`.)

Replace the `clarify` node body:

```python
    async def clarify(state: AgentState) -> dict:
        question = await generate_clarify_reply(
            state["new_message"], state["prefs"], llm
        )
        get_stream_writer()({"type": "clarify", "question": question})
        return {"clarified_once": True, "clarify_question": question}
```

Replace `run_agent` in full:

```python
async def run_agent(
    graph,
    *,
    user_id: str,
    resume_text: str,
    prior_prefs: StructuredPrefs,
    served_keys: list[str],
    message: str,
    thread_id: str,
    user_name: str | None = None,
) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    config.update(langfuse_run_config(user_id, thread_id))
    inputs = {
        "user_id": user_id,
        "resume_text": resume_text,
        "prefs": prior_prefs,
        "served_keys": served_keys,
        "new_message": message,
        "user_name": user_name,
    }
    shown: list[dict] = []
    async for event in graph.astream(inputs, config, stream_mode="custom"):
        if event.get("type") == "result":
            shown.append(event["job"])
        yield event
    snapshot = await graph.aget_state(config)
    yield {
        "type": "done",
        "count": len(shown),
        "served_keys": [job_key(j) for j in shown],
        "prefs": snapshot.values.get("prefs", {}),
    }
```

- [ ] **Step 4: Update `chat/routes.py`**

Replace the full contents of `apps/api/lewis_api/chat/routes.py`:

```python
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lewis_api.agent.graph import run_agent
from lewis_api.auth.deps import get_current_user
from lewis_api.db.base import async_session_maker, get_session
from lewis_api.db.models import ServedJob, User, UserProfile
from lewis_api.schemas import ChatIn

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


def _frame(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    profile = await session.get(UserProfile, user.id)
    resume_text = (profile.resume_text if profile else "") or ""
    prior_prefs = (profile.structured_prefs if profile else {}) or {}
    user_name = (profile.name if profile else None) or None
    served_rows = await session.scalars(
        select(ServedJob.job_key).where(ServedJob.user_id == user.id)
    )
    served_keys = list(served_rows)
    graph = request.app.state.agent_graph
    thread_id = f"{user.id}:{body.conversation_id}"
    user_id = user.id

    async def gen():
        newly_served: list[str] = []
        final_prefs = prior_prefs
        async for event in run_agent(
            graph,
            user_id=str(user_id),
            resume_text=resume_text,
            prior_prefs=prior_prefs,
            served_keys=served_keys,
            message=body.message,
            thread_id=thread_id,
            user_name=user_name,
        ):
            if event["type"] == "done":
                newly_served = event.get("served_keys", [])
                final_prefs = event.get("prefs", prior_prefs)
            yield _frame(event)

        # Use a fresh, request-independent session: the request-scoped `session`
        # may already be torn down by the time the stream finishes. Dedupe keys
        # (they were just excluded from the search, so collisions are unlikely)
        # and guard the commit so a duplicate/constraint error can't crash the
        # stream after results have already been sent to the client.
        deduped = list(dict.fromkeys(newly_served))
        async with async_session_maker() as write_session:
            for key in deduped:
                write_session.add(ServedJob(user_id=user_id, job_key=key))
            write_profile = await write_session.get(UserProfile, user_id)
            if write_profile is not None:
                write_profile.structured_prefs = final_prefs
            try:
                await write_session.commit()
            except Exception:
                logger.exception(
                    "Failed to record served jobs / preferences for user %s", user_id
                )
                await write_session.rollback()

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest -q`
Expected: PASS — full suite (this change touches shared code paths every chat test exercises).

- [ ] **Step 6: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/graph.py apps/api/lewis_api/chat/routes.py apps/api/tests/agent/test_graph.py apps/api/tests/test_chat.py
git commit -m "feat: persist structured_prefs across conversations"
```

---

## Task 7: Agent-initiated first message

**Files:**
- Create: `apps/web/src/lib/greeting.ts`
- Create: `apps/web/src/lib/greeting.test.ts`
- Modify: `apps/web/src/pages/Chat.tsx`
- Modify: `apps/web/src/pages/Chat.test.tsx`

**Interfaces:**
- Consumes: `Profile` type (existing `types.ts`), `useProfile()` (existing `queries.ts`).
- Produces: `greetingText(profile: Profile): string`. Rendered as a `narrative`-kind `Item` in `Chat.tsx` — this is the last shape Task 15 (Phase 4) changes (from a plain dispatch to a `"finalize"` action).

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/lib/greeting.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { greetingText } from "./greeting";
import type { Profile } from "../types";

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    name: null,
    resume_text: "resume",
    raw_prefs_text: null,
    structured_prefs: {},
    ...overrides,
  };
}

describe("greetingText", () => {
  it("prompts a new user with no stored preferences", () => {
    const text = greetingText(profile());
    expect(text).toContain("Tell me what kind of role");
    expect(text).not.toContain("Last time");
  });

  it("greets by name when known", () => {
    const text = greetingText(profile({ name: "Brice" }));
    expect(text.startsWith("Hey, Brice!")).toBe(true);
  });

  it("summarizes stored role and location preferences for a returning user", () => {
    const text = greetingText(
      profile({
        name: "Brice",
        structured_prefs: { role_keywords: ["FDE", "SWE"], locations: ["SF", "NYC"] },
      }),
    );
    expect(text).toContain("Last time you were looking for FDE, SWE in SF, NYC");
  });

  it("summarizes a role preference with no location", () => {
    const text = greetingText(
      profile({ structured_prefs: { role_keywords: ["FDE"] } }),
    );
    expect(text).toContain("Last time you were looking for FDE");
    expect(text).not.toContain(" in ");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- greeting.test.ts`
Expected: FAIL — `Failed to resolve import "./greeting"`.

- [ ] **Step 3: Implement `greeting.ts`**

Create `apps/web/src/lib/greeting.ts`:

```ts
import type { Profile } from "../types";

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

export function greetingText(profile: Profile): string {
  const who = profile.name ? `, ${profile.name}` : "";
  const roles = asStringArray(profile.structured_prefs.role_keywords);
  const locations = asStringArray(profile.structured_prefs.locations);
  if (roles.length > 0) {
    const where = locations.length > 0 ? ` in ${locations.join(", ")}` : "";
    return (
      `Hey${who}! Last time you were looking for ${roles.join(", ")}${where} — ` +
      `still the plan, or has something changed?`
    );
  }
  return (
    `Hey${who}! Tell me what kind of role you're looking for — location, ` +
    `seniority, anything that matters to you — and I'll start searching.`
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- greeting.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the greeting into `Chat.tsx`, update `Chat.test.tsx`**

First, update the `renderChat()` helper in `apps/web/src/pages/Chat.test.tsx` so `useProfile()` has something to resolve (add `beforeEach`/`afterEach` imports to the existing `vitest` import line, and a `stubProfileFetch` helper):

```tsx
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Chat } from "./Chat";
import type { ChatEvent, Profile } from "../types";

vi.mock("../lib/sse", () => ({
  streamChat: vi.fn(),
}));

import { streamChat } from "../lib/sse";

function stubProfileFetch(overrides: Partial<Profile> = {}) {
  const body: Profile = {
    name: null,
    resume_text: "resume",
    raw_prefs_text: null,
    structured_prefs: {},
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), {
      headers: { "content-type": "application/json" },
    })),
  );
}

function renderChat(profileOverrides: Partial<Profile> = {}) {
  stubProfileFetch(profileOverrides);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Chat /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function sendMessage(text: string) {
  await userEvent.type(screen.getByPlaceholderText(/new grad/i), text);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
}
```

(Remove the file's old, now-redundant `import { act, render, screen } ...` and `vi` bare import lines — the block above replaces the top of the file through `sendMessage`. Every existing `it(...)` block below stays exactly as-is; each still calls `renderChat()` with no args, which now also stubs a default empty profile.)

Then add these two new tests inside the existing `describe("Chat", ...)` block:

```tsx
  it("shows a personalized greeting for a returning user with known preferences", async () => {
    renderChat({ name: "Brice", structured_prefs: { role_keywords: ["FDE"], locations: ["SF"] } });
    expect(
      await screen.findByText(/Last time you were looking for FDE in SF/),
    ).toBeInTheDocument();
  });

  it("shows a generic prompt for a new user with no stored preferences, with no LLM call", async () => {
    renderChat();
    expect(
      await screen.findByText(/Tell me what kind of role you're looking for/),
    ).toBeInTheDocument();
    expect(streamChat).not.toHaveBeenCalled();
  });
```

Now update `apps/web/src/pages/Chat.tsx`: add the `useProfile` import and `greetingText` import, add the `profile` query and greeting effect:

```tsx
import { useEffect, useReducer, useRef, useState } from "react";
import { streamChat } from "../lib/sse";
import { greetingText } from "../lib/greeting";
import { CompactJobRow } from "../components/CompactJobRow";
import { Spinner } from "../components/Spinner";
import { useStatusTicker } from "../lib/useStatusTicker";
import { useProfile, useSaveJob } from "../queries";
import type { ChatEvent, RankedJob } from "../types";

type Item =
  | { kind: "user"; text: string }
  | { kind: "clarify"; text: string }
  | { kind: "narrative"; text: string }
  | { kind: "result"; job: RankedJob };

function reducer(items: Item[], ev: Item | { kind: "reset" }): Item[] {
  if (ev.kind === "reset") return [];
  return [...items, ev];
}

export function Chat() {
  const [items, dispatch] = useReducer(reducer, []);
  const [input, setInput] = useState("");
  const [convo, setConvo] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const gotNarrative = useRef(false);
  const gotClarify = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const greetedConvos = useRef<Set<string>>(new Set());
  const { data: profile } = useProfile();
  const save = useSaveJob();
  const tickerText = useStatusTicker(busy, statusText);

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    if (!profile || greetedConvos.current.has(convo)) return;
    greetedConvos.current.add(convo);
    dispatch({ kind: "narrative", text: greetingText(profile) });
  }, [convo, profile]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;
    const message = input.trim();
    setInput("");
    dispatch({ kind: "user", text: message });
    setBusy(true);
    setStatusText("Getting started…"); // neutral placeholder — never a filler phrase
    gotNarrative.current = false;
    gotClarify.current = false;
    abort.current = new AbortController();
    try {
      await streamChat({ message, conversation_id: convo }, (ev: ChatEvent) => {
        if (ev.type === "status") setStatusText(ev.text);
        else if (ev.type === "clarify") {
          gotClarify.current = true;
          dispatch({ kind: "clarify", text: ev.question });
        } else if (ev.type === "narrative") {
          gotNarrative.current = true;
          dispatch({ kind: "narrative", text: ev.text });
        } else if (ev.type === "result") dispatch({ kind: "result", job: ev.job });
        else if (ev.type === "done" && !gotNarrative.current && !gotClarify.current) {
          dispatch({
            kind: "narrative",
            text: `Found ${ev.count} role${ev.count === 1 ? "" : "s"}.`,
          });
        }
      }, abort.current.signal);
    } catch {
      dispatch({ kind: "narrative", text: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
      setStatusText(null);
    }
  }

  function newChat() {
    dispatch({ kind: "reset" });
    setConvo(crypto.randomUUID());
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Find roles</h1>
        <button className="text-sm text-gray-600" onClick={newChat}>New chat</button>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((it, i) => {
          if (it.kind === "user")
            return <div key={i} className="self-end rounded bg-black px-3 py-2 text-white">{it.text}</div>;
          if (it.kind === "clarify")
            return <div key={i} className="rounded bg-gray-100 px-3 py-2">{it.text}</div>;
          if (it.kind === "narrative")
            return <p key={i} className="rounded bg-gray-50 px-3 py-3 leading-relaxed">{it.text}</p>;
          return (
            <CompactJobRow key={i} job={it.job} busy={save.isPending}
              onSave={() => save.mutate(it.job)} />
          );
        })}
        {busy && !gotNarrative.current && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner />
            <span>{tickerText}</span>
          </div>
        )}
      </div>
      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input className="flex-1 rounded border p-2" placeholder="e.g. new grad FDE roles in SF"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="rounded bg-black px-4 text-white" disabled={busy}>Send</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — all existing Chat tests plus the two new greeting tests.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/greeting.ts apps/web/src/lib/greeting.test.ts apps/web/src/pages/Chat.tsx apps/web/src/pages/Chat.test.tsx
git commit -m "feat: Lewis greets first, personalized for returning users"
```

---

# Phase 3 — Visual theme

No behavior changes in this phase — every task below only changes `className` strings (plus one CSS file). Text, `aria-label`s, roles, and `href`/`to` targets are preserved everywhere, so no existing test needs new assertions; each task's "test" step is re-running the existing suite as a regression guard. Final visual confirmation happens in the browser-preview step at the end of this document.

## Task 8: Design tokens

**Files:**
- Modify: `apps/web/src/index.css`

- [ ] **Step 1: Add the `@theme` block**

Replace the full contents of `apps/web/src/index.css`:

```css
@import "tailwindcss";

@theme {
  --color-page: #fafaf9;
  --color-surface: #ffffff;
  --color-fg: #1c1917;
  --color-muted: #78716c;
  --color-border: #e7e5e4;
  --color-accent: #4f46e5;
  --color-accent-foreground: #ffffff;
  --color-success: #16a34a;
  --color-success-foreground: #f0fdf4;
  --color-error: #dc2626;
  --radius-bubble: 1rem;
  --shadow-soft: 0 1px 2px rgb(0 0 0 / 0.05), 0 1px 3px rgb(0 0 0 / 0.08);
}

body {
  background-color: var(--color-page);
  color: var(--color-fg);
}
```

- [ ] **Step 2: Run the frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck && pnpm build`
Expected: PASS — this file has no test coverage of its own; `pnpm build` confirms Tailwind v4 accepts the `@theme` block without error.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/index.css
git commit -m "feat: add chat-first design tokens"
```

---

## Task 9: Restyle entry surfaces (AppLayout, Login, Signup, Onboarding)

**Files:**
- Modify: `apps/web/src/components/AppLayout.tsx`
- Modify: `apps/web/src/pages/Login.tsx`
- Modify: `apps/web/src/pages/Signup.tsx`
- Modify: `apps/web/src/pages/Onboarding.tsx`

**Interfaces:**
- Consumes: tokens from Task 8 (`bg-page`, `bg-surface`, `text-fg`, `text-muted`, `border-border`, `bg-accent`/`text-accent`/`text-accent-foreground`, `text-error`, `rounded-bubble`, `shadow-soft`).

- [ ] **Step 1: Restyle `AppLayout.tsx`**

Replace the full contents of `apps/web/src/components/AppLayout.tsx`:

```tsx
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function AppLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "font-medium text-accent" : "text-muted hover:text-fg";

  return (
    <div className="min-h-screen bg-page">
      <header className="border-b border-border bg-surface px-6 py-3">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <NavLink to="/" className="text-lg font-semibold text-fg">Lewis</NavLink>
          <nav className="flex items-center gap-5 text-sm">
            <NavLink to="/" end className={linkClass}>Chat</NavLink>
            <NavLink to="/saved" className={linkClass}>Saved</NavLink>
            <NavLink to="/onboarding" className={linkClass}>Profile</NavLink>
            <button type="button" onClick={handleLogout} className="text-muted hover:text-fg">
              Logout
            </button>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 2: Restyle `Login.tsx`**

Replace the full contents of `apps/web/src/pages/Login.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/login", { email, password });
      await refresh(); // wait for the "me" query to refetch before routing (guards read it)
      nav("/");
    } catch {
      setError("Invalid email or password");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3 rounded-bubble bg-surface p-8 shadow-soft">
        <h1 className="text-2xl font-semibold text-fg">Log in to Lewis</h1>
        <input aria-label="email" className="rounded-lg border border-border p-2 text-fg" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input aria-label="password" type="password" className="rounded-lg border border-border p-2 text-fg"
          placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-error">{error}</p>}
        <button className="rounded-lg bg-accent p-2 text-accent-foreground" type="submit">Log in</button>
        <Link className="text-sm text-accent" to="/signup">Need an account? Sign up</Link>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Restyle `Signup.tsx`**

Replace the full contents of `apps/web/src/pages/Signup.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/signup", { email, password });
      await refresh(); // wait for the "me" query to refetch before routing (guards read it)
      nav("/");
    } catch {
      setError("Could not sign up — that email may already be registered.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3 rounded-bubble bg-surface p-8 shadow-soft">
        <h1 className="text-2xl font-semibold text-fg">Create your Lewis account</h1>
        <input aria-label="email" className="rounded-lg border border-border p-2 text-fg" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input aria-label="password" type="password" className="rounded-lg border border-border p-2 text-fg"
          placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-error">{error}</p>}
        <button className="rounded-lg bg-accent p-2 text-accent-foreground" type="submit">Sign up</button>
        <Link className="text-sm text-accent" to="/login">Already have an account? Log in</Link>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Restyle `Onboarding.tsx`**

Replace the full contents of `apps/web/src/pages/Onboarding.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();

  const [fileName, setFileName] = useState("");

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setBusy(true);
    setError("");
    try {
      await api.uploadFile("/profile/resume", file);
    } catch {
      setError("Upload failed — please use a PDF or DOCX.");
      setBusy(false);
      return;
    }
    if (name.trim()) {
      try {
        await api.put("/profile/name", { name: name.trim() });
      } catch {
        // Name personalization is a nice-to-have — don't block onboarding
        // completion or show the resume-specific error for a name-PUT failure.
        console.error("Failed to save name during onboarding");
      }
    }
    await qc.invalidateQueries({ queryKey: ["profile"] });
    nav("/");
    setBusy(false);
  }

  return (
    <div className="mx-auto mt-16 max-w-md p-6">
      <h1 className="text-2xl font-semibold text-fg">Upload your resume</h1>
      <p className="mt-2 text-muted">
        PDF or DOCX. We use it to match roles to you.
      </p>

      <label className="mt-6 block text-sm font-medium text-fg">
        What should we call you?
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your first name"
          disabled={busy}
          className="mt-1 w-full rounded-lg border border-border bg-surface p-2 font-normal text-fg"
        />
      </label>

      <label
        className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-bubble border-2 border-dashed border-border bg-surface px-6 py-10 text-center shadow-soft transition hover:border-accent ${
          busy ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <span className="text-lg font-medium text-fg">
          {busy ? "Uploading…" : "Choose a PDF or DOCX file"}
        </span>
        <span className="mt-1 text-sm text-muted">
          {fileName || "Click here to browse"}
        </span>
        <input
          aria-label="resume"
          type="file"
          accept=".pdf,.docx"
          onChange={onFile}
          disabled={busy}
          className="hidden"
        />
      </label>

      {error && <p className="mt-3 text-error">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Run the frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — `AppLayout.test.tsx`, `auth.test.tsx` (Login), and `Onboarding.test.tsx` all still pass unchanged.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/AppLayout.tsx apps/web/src/pages/Login.tsx apps/web/src/pages/Signup.tsx apps/web/src/pages/Onboarding.tsx
git commit -m "style: apply chat-first theme to entry surfaces"
```

---

## Task 10: Restyle the chat surface (Chat, CompactJobRow, Spinner)

**Files:**
- Modify: `apps/web/src/pages/Chat.tsx`
- Modify: `apps/web/src/components/CompactJobRow.tsx`
- Modify: `apps/web/src/components/Spinner.tsx`

- [ ] **Step 1: Restyle `Chat.tsx`**

In `apps/web/src/pages/Chat.tsx` (as it stands after Task 7 / Phase 2), replace only the `return (...)` JSX block with:

```tsx
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Find roles</h1>
        <button className="text-sm text-muted hover:text-fg" onClick={newChat}>New chat</button>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((it, i) => {
          if (it.kind === "user")
            return (
              <div key={i} className="self-end rounded-bubble bg-accent px-4 py-2 text-accent-foreground">
                {it.text}
              </div>
            );
          if (it.kind === "clarify")
            return (
              <div key={i} className="rounded-bubble bg-surface px-4 py-2 text-fg shadow-soft">
                {it.text}
              </div>
            );
          if (it.kind === "narrative")
            return (
              <p key={i} className="rounded-bubble bg-surface px-4 py-3 leading-relaxed text-fg shadow-soft">
                {it.text}
              </p>
            );
          return (
            <CompactJobRow key={i} job={it.job} busy={save.isPending}
              onSave={() => save.mutate(it.job)} />
          );
        })}
        {busy && !gotNarrative.current && (
          <div className="flex items-center gap-2 text-sm text-muted">
            <Spinner />
            <span>{tickerText}</span>
          </div>
        )}
      </div>
      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input className="flex-1 rounded-lg border border-border bg-surface p-2 text-fg"
          placeholder="e.g. new grad FDE roles in SF"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="rounded-lg bg-accent px-4 text-accent-foreground" disabled={busy}>Send</button>
      </form>
    </div>
  );
```

- [ ] **Step 2: Restyle `CompactJobRow.tsx`**

Replace the full contents of `apps/web/src/components/CompactJobRow.tsx`:

```tsx
import type { RankedJob } from "../types";

export function CompactJobRow({
  job, onSave, busy,
}: {
  job: RankedJob;
  onSave: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 text-sm last:border-b-0">
      <div className="min-w-0">
        <a href={job.url} target="_blank" rel="noreferrer"
          className="font-medium text-accent hover:underline">{job.title}</a>
        <p className="truncate text-muted">
          {job.company}{job.location ? ` · ${job.location}` : ""}
        </p>
      </div>
      <button onClick={onSave} disabled={busy}
        className="shrink-0 rounded-lg border border-border px-2 py-1 text-xs text-fg hover:bg-page">
        Save
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Restyle `Spinner.tsx`**

Replace the full contents of `apps/web/src/components/Spinner.tsx`:

```tsx
export function Spinner() {
  return (
    <span className="inline-flex gap-1" role="status" aria-label="Loading">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" />
    </span>
  );
}
```

- [ ] **Step 4: Run the frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: PASS — `Chat.test.tsx`, `CompactJobRow.test.tsx`, `Spinner.test.tsx` all pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/Chat.tsx apps/web/src/components/CompactJobRow.tsx apps/web/src/components/Spinner.tsx
git commit -m "style: apply chat-first theme to the chat surface"
```

---

## Task 11: Restyle the saved-jobs surface (Saved, JobCard)

**Files:**
- Modify: `apps/web/src/pages/Saved.tsx`
- Modify: `apps/web/src/components/JobCard.tsx`

- [ ] **Step 1: Restyle `Saved.tsx`**

Replace the full contents of `apps/web/src/pages/Saved.tsx`:

```tsx
import { JobCard } from "../components/JobCard";
import { useJobs, useUnsaveJob } from "../queries";

export function Saved() {
  const { data, isLoading } = useJobs();
  const unsave = useUnsaveJob();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Saved jobs</h1>
      </div>
      {isLoading && <p className="text-muted">Loading…</p>}
      {data && data.length === 0 && <p className="text-muted">No saved jobs yet.</p>}
      {data?.map((job) => (
        <JobCard
          key={job.id}
          job={job}
          action="unsave"
          busy={unsave.isPending}
          onAction={() => unsave.mutate(job.id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Restyle `JobCard.tsx`**

Replace the full contents of `apps/web/src/components/JobCard.tsx`:

```tsx
import type { RankedJob, SavedJob } from "../types";

export function JobCard({
  job, action, onAction, busy,
}: {
  job: RankedJob | SavedJob;
  action: "save" | "unsave";
  onAction: () => void;
  busy?: boolean;
}) {
  return (
    <div className="rounded-bubble border border-border bg-surface p-4 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <a href={job.url} target="_blank" rel="noreferrer"
            className="font-semibold text-accent hover:underline">{job.title}</a>
          <p className="text-sm text-muted">
            {job.company}{job.location ? ` · ${job.location}` : ""}
          </p>
        </div>
        {typeof job.score === "number" && (
          <span className="rounded-full bg-success-foreground px-2 py-1 text-xs font-medium text-success">
            {job.score}
          </span>
        )}
      </div>
      {job.reason && <p className="mt-2 text-sm text-fg">{job.reason}</p>}
      <button onClick={onAction} disabled={busy}
        className="mt-3 rounded-lg border border-border px-3 py-1 text-sm text-fg hover:bg-page">
        {action === "save" ? "Save" : "Remove"}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Run the frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck && pnpm build`
Expected: PASS — `Saved.test.tsx`, `JobCard.test.tsx` pass unchanged; `pnpm build` confirms the whole app still compiles.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Saved.tsx apps/web/src/components/JobCard.tsx
git commit -m "style: apply chat-first theme to the saved-jobs surface"
```

---

# Phase 4 — Real token streaming

## Task 12: `LLM.stream()` capability

**Files:**
- Modify: `apps/api/lewis_api/agent/llm.py`
- Modify: `apps/api/tests/agent/test_llm.py`

**Interfaces:**
- Produces: `LLM.stream(system: str, user: str) -> AsyncIterator[str]`, replacing `LLM.complete()` (removed — after Task 13, nothing calls `complete()` anymore). Consumed by Task 13's `narrate.py`/`clarify.py`.

- [ ] **Step 1: Write the failing test**

Replace the full contents of `apps/api/tests/agent/test_llm.py`:

```python
import pytest

from lewis_api.agent.llm import AnthropicLLM


class _FinalMessage:
    def __init__(self, usage=None):
        self.usage = usage


class _FakeMessageStream:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _gen(self):
        for c in self._chunks:
            yield c

    @property
    def text_stream(self):
        return self._gen()

    async def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final

    def stream(self, **kwargs):
        return _FakeMessageStream(self._chunks, self._final)


class _FakeClient:
    def __init__(self, chunks, final=None):
        self.messages = _FakeMessages(chunks, final or _FinalMessage())


@pytest.mark.asyncio
async def test_stream_yields_chunks_in_order():
    llm = AnthropicLLM(client=_FakeClient(["Hel", "lo ", "there"]), model="fake-model")
    chunks = [c async for c in llm.stream(system="s", user="u")]
    assert chunks == ["Hel", "lo ", "there"]


@pytest.mark.asyncio
async def test_stream_yields_nothing_for_empty_response():
    llm = AnthropicLLM(client=_FakeClient([]), model="fake-model")
    chunks = [c async for c in llm.stream(system="s", user="u")]
    assert chunks == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: FAIL — `AttributeError: 'AnthropicLLM' object has no attribute 'stream'`.

- [ ] **Step 3: Implement `stream()`, remove `complete()`**

Replace the full contents of `apps/api/lewis_api/agent/llm.py`:

```python
from collections.abc import AsyncIterator
from typing import Protocol

from anthropic import AsyncAnthropic

from lewis_api.agent.tracing import observe_generation
from lewis_api.config import get_settings


class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...

    def stream(self, system: str, user: str) -> AsyncIterator[str]: ...


def _usage_details(resp) -> dict | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return {"input": usage.input_tokens, "output": usage.output_tokens}


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.agent_model

    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict:
        with observe_generation(
            tool_name, self._model, {"system": system, "user": user}
        ) as generation:
            resp = await self._client.messages.create(
                model=self._model,
                # Ranking ~50 jobs needs well over 1500 output tokens; a low cap
                # truncates the tool call and yields empty results. Billing is on
                # actual output, so a high ceiling is free insurance.
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": tool_name,
                        "description": tool_name,
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
            result = {}
            for block in resp.content:
                if block.type == "tool_use":
                    result = dict(block.input)
                    break
            generation.update(output=result, usage_details=_usage_details(resp))
            return result

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        with observe_generation(
            "stream", self._model, {"system": system, "user": user}
        ) as generation:
            full_text = ""
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                async for chunk in stream.text_stream:
                    full_text += chunk
                    yield chunk
                final = await stream.get_final_message()
            generation.update(output=full_text, usage_details=_usage_details(final))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/agent/test_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/llm.py apps/api/tests/agent/test_llm.py
git commit -m "feat: add LLM.stream(), remove now-unused complete()"
```

---

## Task 13: Streaming narrative & clarify generation

**Files:**
- Modify: `apps/api/lewis_api/agent/narrate.py`
- Modify: `apps/api/tests/agent/test_narrate.py`
- Modify: `apps/api/lewis_api/agent/clarify.py`
- Modify: `apps/api/tests/agent/test_clarify.py`

**Interfaces:**
- Consumes: `LLM.stream()` (Task 12).
- Produces: `stream_narrative_results(...) -> AsyncIterator[str]`, `fallback_text(n: int) -> str` (replacing `narrate_results`); `stream_clarify_reply(...) -> AsyncIterator[str]` (replacing `generate_clarify_reply`, keeping `CLARIFY_TEXT`). Both raise on LLM failure — callers (Task 14's `graph.py`) handle fallback. Consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `apps/api/tests/agent/test_narrate.py`:

```python
import pytest

from lewis_api.agent.narrate import fallback_text, stream_narrative_results

RANKED = [
    {
        "external_id": "1",
        "title": "FDE",
        "company": "Ramp",
        "location": "SF",
        "score": 92,
        "reason": "Matches your backend + customer-facing experience",
    },
    {
        "external_id": "2",
        "title": "Support Engineer",
        "company": "GitLab",
        "location": "Remote",
        "score": 61,
        "reason": "Lower seniority but remote-friendly",
    },
]


class FakeLLM:
    def __init__(self, chunks=None, raise_exc=None):
        self.chunks = chunks or []
        self.raise_exc = raise_exc
        self.calls = []

    async def stream(self, system, user):
        self.calls.append((system, user))
        if self.raise_exc:
            raise self.raise_exc
        for c in self.chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_narrative_yields_chunks_with_context():
    llm = FakeLLM(chunks=["Hey Brice, ", "I found 2 roles..."])
    chunks = [
        c
        async for c in stream_narrative_results(
            RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        )
    ]
    assert chunks == ["Hey Brice, ", "I found 2 roles..."]
    assert len(llm.calls) == 1
    _, user = llm.calls[0]
    assert "Brice" in user
    assert "FDE" in user
    assert "Ramp" in user


@pytest.mark.asyncio
async def test_stream_narrative_skips_llm_call_when_no_results():
    llm = FakeLLM(chunks=["should not be used"])
    chunks = [
        c
        async for c in stream_narrative_results(
            [], {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        )
    ]
    assert chunks == [
        "I didn't find any roles matching that this time — try broadening your "
        "criteria (location, seniority, or role type) and I'll take another look."
    ]
    assert llm.calls == []


@pytest.mark.asyncio
async def test_stream_narrative_raises_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        async for _ in stream_narrative_results(
            RANKED, {"role_keywords": ["fde"]}, "resume text", "Brice", llm
        ):
            pass


@pytest.mark.asyncio
async def test_stream_narrative_uses_generic_greeting_when_no_name():
    llm = FakeLLM(chunks=["Hi there, found some roles."])
    chunks = [
        c async for c in stream_narrative_results(RANKED, {}, "resume", None, llm)
    ]
    assert chunks == ["Hi there, found some roles."]
    _, user = llm.calls[0]
    assert "there" in user


def test_fallback_text():
    assert fallback_text(1) == "I found 1 job matching your search."
    assert fallback_text(2) == "I found 2 jobs matching your search."
```

Replace the full contents of `apps/api/tests/agent/test_clarify.py`:

```python
import pytest

from lewis_api.agent.clarify import CLARIFY_TEXT, stream_clarify_reply


class FakeLLM:
    def __init__(self, chunks=None, raise_exc=None):
        self.chunks = chunks or []
        self.raise_exc = raise_exc
        self.calls = []

    async def stream(self, system, user):
        self.calls.append((system, user))
        if self.raise_exc:
            raise self.raise_exc
        for c in self.chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_clarify_reply_includes_message_and_missing_fields():
    llm = FakeLLM(chunks=["Hey! ", "Where are you looking, and what level?"])
    chunks = [c async for c in stream_clarify_reply("hi there", {}, llm)]
    assert chunks == ["Hey! ", "Where are you looking, and what level?"]
    _, user = llm.calls[0]
    assert "hi there" in user
    assert "role" in user
    assert "location or remote work" in user
    assert "seniority level" in user


@pytest.mark.asyncio
async def test_stream_clarify_reply_raises_on_llm_error():
    llm = FakeLLM(raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        async for _ in stream_clarify_reply("hi", {}, llm):
            pass


def test_clarify_text_fallback_is_a_nonempty_static_string():
    assert isinstance(CLARIFY_TEXT, str) and CLARIFY_TEXT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_narrate.py tests/agent/test_clarify.py -v`
Expected: FAIL — `ImportError: cannot import name 'stream_narrative_results'` / `'stream_clarify_reply'`.

- [ ] **Step 3: Rewrite `narrate.py`**

Replace the full contents of `apps/api/lewis_api/agent/narrate.py`:

```python
import json
from collections.abc import AsyncIterator

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import RankedJob, StructuredPrefs

_SYSTEM = (
    "You are a friendly job-search assistant writing a short summary of search "
    "results directly to the user in a chat. Address them by name. Say how many "
    "jobs you found. Call out the top-ranked result by title and company and "
    "explain briefly why it fits, tying back to their resume or preferences. If "
    "another result is a bit of a stretch from what they asked for, mention it "
    "and say why it might still be worth a look. 2-4 sentences, conversational, "
    "no bullet points, no markdown."
)

_NO_RESULTS = (
    "I didn't find any roles matching that this time — try broadening your "
    "criteria (location, seniority, or role type) and I'll take another look."
)


def fallback_text(n: int) -> str:
    return f"I found {n} job{'s' if n != 1 else ''} matching your search."


def _compact(ranked: list[RankedJob]) -> list[dict]:
    return [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "reason": j.get("reason"),
        }
        for j in ranked
    ]


async def stream_narrative_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    resume_text: str,
    user_name: str | None,
    llm: LLM,
) -> AsyncIterator[str]:
    """Yields the narrative text as chunks arrive from the LLM. Raises on LLM
    failure — the caller (graph.py's respond node) falls back to
    fallback_text(), since by the time a mid-stream error can occur, earlier
    chunks may already be visible to the user."""
    if not ranked:
        yield _NO_RESULTS
        return
    user = (
        f"User's name: {user_name or 'there'}\n\n"
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Ranked results, best first:\n{json.dumps(_compact(ranked))}"
    )
    async for chunk in llm.stream(system=_SYSTEM, user=user):
        yield chunk
```

- [ ] **Step 4: Rewrite `clarify.py`**

Replace the full contents of `apps/api/lewis_api/agent/clarify.py`:

```python
from collections.abc import AsyncIterator

from lewis_api.agent.llm import LLM
from lewis_api.agent.prefs import missing_fields
from lewis_api.agent.state import StructuredPrefs

CLARIFY_TEXT = (
    "To narrow this down: which locations are you targeting, or is remote OK? "
    "And what seniority (e.g. new grad, mid, senior)?"
)

_SYSTEM = (
    "You are Lewis, a friendly job-search assistant chatting with a user in a "
    "job-search app. They haven't given you enough to search yet. Briefly "
    "acknowledge what they just said — even if it's just a greeting or small "
    "talk unrelated to a job search — then ask a short, natural question "
    "covering what's still missing. 1-2 sentences, conversational, no bullet "
    "points, no markdown."
)


async def stream_clarify_reply(
    user_message: str, prefs: StructuredPrefs, llm: LLM
) -> AsyncIterator[str]:
    """Yields the clarify reply as chunks arrive from the LLM. Raises on LLM
    failure — the caller (graph.py's clarify node) falls back to
    CLARIFY_TEXT, since by the time a mid-stream error can occur, earlier
    chunks may already be visible to the user."""
    missing = missing_fields(prefs)
    user = (
        f"User just said: {user_message!r}\n\n"
        f"Preferences gathered so far: {prefs}\n\n"
        f"Still need to ask about: {', '.join(missing)}"
    )
    async for chunk in llm.stream(system=_SYSTEM, user=user):
        yield chunk
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/agent/test_narrate.py tests/agent/test_clarify.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/narrate.py apps/api/tests/agent/test_narrate.py apps/api/lewis_api/agent/clarify.py apps/api/tests/agent/test_clarify.py
git commit -m "feat: switch narrative and clarify generation to streaming"
```

---

## Task 14: Wire streaming into the graph

**Files:**
- Modify: `apps/api/lewis_api/agent/graph.py`
- Modify: `apps/api/tests/agent/test_graph.py`

**Interfaces:**
- Consumes: `stream_narrative_results`, `fallback_text` (Task 13), `stream_clarify_reply`, `CLARIFY_TEXT` (Task 13).
- Produces: two new SSE event types on the wire — `{"type": "narrative_delta", "text": str}` and `{"type": "clarify_delta", "text": str}` — sent before the existing terminal `narrative`/`clarify` events, which are unchanged in shape. Consumed by Task 15's frontend.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/agent/test_graph.py`, replace the `FakeLLM` class:

```python
class FakeLLM:
    def __init__(
        self, prefs_payload, rank_payload, narrative_text="Here's what I found."
    ):
        self.prefs_payload = prefs_payload
        self.rank_payload = rank_payload
        self.narrative_text = narrative_text
        self.stream_calls = []

    async def structured(self, system, user, tool_name, schema):
        if tool_name == "record_preferences":
            return self.prefs_payload
        return self.rank_payload

    async def stream(self, system, user):
        self.stream_calls.append(user)
        for chunk in self.narrative_text.split(" "):
            yield chunk + " "
```

In `test_clear_query_streams_results_and_reports_served`, replace the last assertion:

```python
    # Proves the run_agent -> AgentState -> respond -> narrate_results hop
    # actually threads user_name through, not just the two endpoints.
    assert any("Brice" in call for call in llm.complete_calls)
```

with:

```python
    # Proves the run_agent -> AgentState -> respond -> stream_narrative_results
    # hop actually threads user_name through, not just the two endpoints.
    assert any("Brice" in call for call in llm.stream_calls)
    assert "narrative_delta" in types
    assert types.index("narrative_delta") < types.index("narrative")
```

In `test_vague_query_asks_one_clarify_then_searches`, update the assertion on `types_first`:

```python
    assert first[0]["type"] == "status"  # "Reading your resume..." comes first now
    assert "clarify" in types_first and types_first[-1] == "done"
```

with:

```python
    assert first[0]["type"] == "status"  # "Reading your resume..." comes first now
    assert "clarify_delta" in types_first
    assert types_first.index("clarify_delta") < types_first.index("clarify")
    assert "clarify" in types_first and types_first[-1] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/agent/test_graph.py -v`
Expected: FAIL — `AttributeError: 'FakeLLM' object has no attribute 'complete'` (from the old `narrate_results`/`generate_clarify_reply` imports still calling `.complete()`), and the new delta assertions have nothing to match yet.

- [ ] **Step 3: Update `graph.py`'s imports and the `clarify`/`respond` nodes**

In `apps/api/lewis_api/agent/graph.py`, update the imports:

```python
import logging
from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.clarify import CLARIFY_TEXT, stream_clarify_reply
from lewis_api.agent.narrate import fallback_text, stream_narrative_results
from lewis_api.agent.normalize import job_key
from lewis_api.agent.prefilter import prefilter
from lewis_api.agent.prefs import is_sufficient, parse_prefs
from lewis_api.agent.rank import rank_jobs
from lewis_api.agent.select_results import select_results
from lewis_api.agent.seniority import filter_by_seniority
from lewis_api.agent.state import AgentState, StructuredPrefs
from lewis_api.agent.tracing import langfuse_run_config
from lewis_api.config import get_settings

logger = logging.getLogger(__name__)
```

Replace the `clarify` node:

```python
    async def clarify(state: AgentState) -> dict:
        writer = get_stream_writer()
        full_text = ""
        try:
            async for chunk in stream_clarify_reply(
                state["new_message"], state["prefs"], llm
            ):
                full_text += chunk
                writer({"type": "clarify_delta", "text": chunk})
        except Exception:  # noqa: BLE001
            full_text = CLARIFY_TEXT
        writer({"type": "clarify", "question": full_text})
        return {"clarified_once": True, "clarify_question": full_text}
```

Replace the `respond` node:

```python
    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        ranked = state.get("ranked", [])
        eligible = filter_by_seniority(ranked, state["prefs"])
        top = select_results(eligible, state["prefs"], get_settings().max_results)
        logger.info(
            "respond funnel: ranked=%d eligible=%d top=%d",
            len(ranked),
            len(eligible),
            len(top),
        )
        writer({"type": "status", "text": "Writing up what I found…"})
        full_text = ""
        try:
            async for chunk in stream_narrative_results(
                top,
                state["prefs"],
                state.get("resume_text", ""),
                state.get("user_name"),
                llm,
            ):
                full_text += chunk
                writer({"type": "narrative_delta", "text": chunk})
        except Exception:  # noqa: BLE001
            full_text = fallback_text(len(top))
        writer({"type": "narrative", "text": full_text})
        for job in top:
            writer({"type": "result", "job": job})
        return {"ranked": top}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest -q`
Expected: PASS — full suite.

- [ ] **Step 5: Commit**

```bash
cd apps/api && uv run ruff check . && uv run black --check .
git add apps/api/lewis_api/agent/graph.py apps/api/tests/agent/test_graph.py
git commit -m "feat: stream narrative and clarify text over SSE"
```

---

## Task 15: Frontend delta rendering

**Files:**
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/pages/Chat.tsx`
- Modify: `apps/web/src/pages/Chat.test.tsx`

**Interfaces:**
- Consumes: `narrative_delta`/`clarify_delta` SSE events (Task 14).

- [ ] **Step 1: Write the failing tests**

Add these two tests inside the existing `describe("Chat", ...)` block in `apps/web/src/pages/Chat.test.tsx`:

```tsx
  it("renders narrative text incrementally as delta events arrive, then reconciles to the final text", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative_delta", text: "Hey " });
        onEvent({ type: "narrative_delta", text: "Brice, " });
        onEvent({ type: "narrative", text: "Hey Brice, I found 1 great match." });
        onEvent({
          type: "result",
          job: {
            source: "ashby", company: "Ramp", title: "FDE", location: "SF",
            url: "https://x", score: 90, reason: "great",
          },
        });
        onEvent({ type: "done", count: 1 });
      },
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(
      await screen.findByText("Hey Brice, I found 1 great match."),
    ).toBeInTheDocument();
  });

  it("hides the spinner/ticker as soon as the first narrative delta arrives", async () => {
    let resolveStream!: () => void;
    vi.mocked(streamChat).mockImplementation(
      (_body: unknown, onEvent: (e: ChatEvent) => void) =>
        new Promise<void>((resolve) => {
          onEvent({ type: "narrative_delta", text: "Hey, " });
          resolveStream = resolve;
        }),
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByText("Hey, ")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    await act(async () => {
      resolveStream();
    });
  });

  it("streams a clarify reply incrementally", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "clarify_delta", text: "Hey! " });
        onEvent({ type: "clarify_delta", text: "Where are you looking?" });
        onEvent({ type: "clarify", question: "Hey! Where are you looking?" });
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("hi");
    expect(await screen.findByText("Hey! Where are you looking?")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- Chat.test.tsx`
Expected: FAIL — TypeScript rejects `narrative_delta`/`clarify_delta` as unknown `ChatEvent` variants, and the component doesn't handle them yet (text never appears).

- [ ] **Step 3: Update `types.ts`**

In `apps/web/src/types.ts`, replace the `ChatEvent` type:

```ts
export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "clarify_delta"; text: string }
  | { type: "clarify"; question: string }
  | { type: "narrative_delta"; text: string }
  | { type: "narrative"; text: string }
  | { type: "result"; job: RankedJob }
  | { type: "done"; count: number };
```

- [ ] **Step 4: Rewrite `Chat.tsx`'s reducer and event handling**

Replace the full contents of `apps/web/src/pages/Chat.tsx`:

```tsx
import { useEffect, useReducer, useRef, useState } from "react";
import { streamChat } from "../lib/sse";
import { greetingText } from "../lib/greeting";
import { CompactJobRow } from "../components/CompactJobRow";
import { Spinner } from "../components/Spinner";
import { useStatusTicker } from "../lib/useStatusTicker";
import { useProfile, useSaveJob } from "../queries";
import type { ChatEvent, RankedJob } from "../types";

type Item =
  | { kind: "user"; text: string }
  | { kind: "clarify"; text: string; streaming?: boolean }
  | { kind: "narrative"; text: string; streaming?: boolean }
  | { kind: "result"; job: RankedJob };

type Action =
  | { kind: "reset" }
  | { kind: "user"; text: string }
  | { kind: "delta"; itemKind: "clarify" | "narrative"; text: string }
  | { kind: "finalize"; itemKind: "clarify" | "narrative"; text: string }
  | { kind: "result"; job: RankedJob };

function reducer(items: Item[], action: Action): Item[] {
  const last = items[items.length - 1];
  switch (action.kind) {
    case "reset":
      return [];
    case "user":
      return [...items, { kind: "user", text: action.text }];
    case "delta":
      if (last && last.kind === action.itemKind && last.streaming) {
        return [...items.slice(0, -1), { ...last, text: last.text + action.text }];
      }
      return [...items, { kind: action.itemKind, text: action.text, streaming: true }];
    case "finalize":
      if (last && last.kind === action.itemKind && last.streaming) {
        return [...items.slice(0, -1), { ...last, text: action.text, streaming: false }];
      }
      return [...items, { kind: action.itemKind, text: action.text }];
    case "result":
      return [...items, { kind: "result", job: action.job }];
  }
}

export function Chat() {
  const [items, dispatch] = useReducer(reducer, []);
  const [input, setInput] = useState("");
  const [convo, setConvo] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const gotNarrative = useRef(false);
  const gotClarify = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const greetedConvos = useRef<Set<string>>(new Set());
  const { data: profile } = useProfile();
  const save = useSaveJob();
  const tickerText = useStatusTicker(busy, statusText);

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    if (!profile || greetedConvos.current.has(convo)) return;
    greetedConvos.current.add(convo);
    dispatch({ kind: "finalize", itemKind: "narrative", text: greetingText(profile) });
  }, [convo, profile]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;
    const message = input.trim();
    setInput("");
    dispatch({ kind: "user", text: message });
    setBusy(true);
    setStatusText("Getting started…"); // neutral placeholder — never a filler phrase
    gotNarrative.current = false;
    gotClarify.current = false;
    abort.current = new AbortController();
    try {
      await streamChat({ message, conversation_id: convo }, (ev: ChatEvent) => {
        if (ev.type === "status") setStatusText(ev.text);
        else if (ev.type === "clarify_delta") {
          gotClarify.current = true;
          dispatch({ kind: "delta", itemKind: "clarify", text: ev.text });
        } else if (ev.type === "clarify") {
          gotClarify.current = true;
          dispatch({ kind: "finalize", itemKind: "clarify", text: ev.question });
        } else if (ev.type === "narrative_delta") {
          gotNarrative.current = true;
          dispatch({ kind: "delta", itemKind: "narrative", text: ev.text });
        } else if (ev.type === "narrative") {
          gotNarrative.current = true;
          dispatch({ kind: "finalize", itemKind: "narrative", text: ev.text });
        } else if (ev.type === "result") dispatch({ kind: "result", job: ev.job });
        else if (ev.type === "done" && !gotNarrative.current && !gotClarify.current) {
          dispatch({
            kind: "finalize",
            itemKind: "narrative",
            text: `Found ${ev.count} role${ev.count === 1 ? "" : "s"}.`,
          });
        }
      }, abort.current.signal);
    } catch {
      dispatch({ kind: "finalize", itemKind: "narrative", text: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
      setStatusText(null);
    }
  }

  function newChat() {
    dispatch({ kind: "reset" });
    setConvo(crypto.randomUUID());
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Find roles</h1>
        <button className="text-sm text-muted hover:text-fg" onClick={newChat}>New chat</button>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((it, i) => {
          if (it.kind === "user")
            return (
              <div key={i} className="self-end rounded-bubble bg-accent px-4 py-2 text-accent-foreground">
                {it.text}
              </div>
            );
          if (it.kind === "clarify")
            return (
              <div key={i} className="rounded-bubble bg-surface px-4 py-2 text-fg shadow-soft">
                {it.text}
              </div>
            );
          if (it.kind === "narrative")
            return (
              <p key={i} className="rounded-bubble bg-surface px-4 py-3 leading-relaxed text-fg shadow-soft">
                {it.text}
              </p>
            );
          return (
            <CompactJobRow key={i} job={it.job} busy={save.isPending}
              onSave={() => save.mutate(it.job)} />
          );
        })}
        {busy && !gotNarrative.current && (
          <div className="flex items-center gap-2 text-sm text-muted">
            <Spinner />
            <span>{tickerText}</span>
          </div>
        )}
      </div>
      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input className="flex-1 rounded-lg border border-border bg-surface p-2 text-fg"
          placeholder="e.g. new grad FDE roles in SF"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="rounded-lg bg-accent px-4 text-accent-foreground" disabled={busy}>Send</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && pnpm test && pnpm typecheck && pnpm build`
Expected: PASS — full frontend suite, including all pre-existing Chat tests (they never simulate deltas, so the "sudden complete event" path is unaffected) plus the three new streaming tests.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/types.ts apps/web/src/pages/Chat.tsx apps/web/src/pages/Chat.test.tsx
git commit -m "feat: render narrative and clarify text as it streams in"
```

---

# Final verification

- [ ] **Step 1: Full backend suite**

Run: `cd apps/api && uv run pytest -q && uv run ruff check . && uv run black --check .`
Expected: all green.

- [ ] **Step 2: Full frontend suite**

Run: `cd apps/web && pnpm test && pnpm typecheck && pnpm build`
Expected: all green.

- [ ] **Step 3: Manual browser walkthrough**

Start both servers (`cd apps/api && uv run uvicorn lewis_api.main:app --reload --port 8000`, `cd apps/web && pnpm dev`) and, via the Browser pane tool, walk through: sign up → onboarding (upload résumé, see the new theme) → land on Chat and see Lewis's opening greeting appear → use the header to reach Saved and back → say something unrelated to jobs ("hey, how's it going") and confirm Lewis acknowledges it before asking for preferences → give preferences and watch the reply stream in → click "New chat" and confirm the greeting now references the stored preferences → reload the page entirely and start a new conversation, confirming preferences still carry over. Screenshot key screens.

- [ ] **Step 4: Update `status.md`**

Record that this plan is fully implemented, note the PR is ready, and that PR #1 (Langfuse observability) is still separately pending merge.

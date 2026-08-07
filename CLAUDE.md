# Lewis — Workflow

## Code Priorities

When writing code, prioritize:

1. **Human-understandable** — a reader should be able to follow it without
   extra explanation.
2. **Concise** — no more code than the problem requires.

When a new case doesn't fit existing code cleanly, prefer altering or
removing something upstream over bolting on another exception or special
case. An upstream fix keeps the code simple for the *next* change too;
another exception just compounds.

When these two priorities conflict with each other, use judgement.

## Orchestrator & Delegation

For new features or creative work, the standard `superpowers:brainstorming` →
`superpowers:writing-plans` flow applies as usual.

Once a plan or spec is approved, the main thread acts as **orchestrator only**:

- Do not `Edit`/`Write`/implement directly. Dispatch subagents via the `Agent`
  tool for every unit of work — implementation, codebase exploration
  (`Explore` agent), and external research (docs/library/API lookups).
- The orchestrator's job: review each subagent's diff/output, decide the next
  delegation, and keep `status.md` current.
- Exception: read-only/verification commands the orchestrator runs itself to
  check a subagent's work (`git status`, running tests, reading a file) are
  fine — those aren't "implementation."
- Use `superpowers:subagent-driven-development` and
  `superpowers:dispatching-parallel-agents` for delegation mechanics rather
  than improvising.

## status.md Protocol

- Session start: read `status.md` (and memory files under
  `/Users/briceparrott/.claude/projects/-Users-briceparrott-coding-projects-Lewis/memory/`)
  before doing anything else.
- `status.md` is the single resume-point for the project — it links out to
  `docs/superpowers/plans/` and `docs/superpowers/specs/` rather than
  duplicating their content.
- Update `status.md` after each meaningful chunk of delegated work completes
  (not just at natural session end), since a session can crash at any time.

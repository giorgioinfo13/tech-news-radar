# Project instructions

## Project context

Tech News Radar is a personal news reader for technology, AI, software development,
and economics. Keep it simple, readable, and suitable for future collaboration.

- `frontend/`: React, TypeScript, Vite, and Tailwind CSS.
- `backend/`: FastAPI, configuration, SQLAlchemy models, Alembic migrations, and backend tests.
- `docs/`: local development instructions and architecture decisions.
- `README.md` and `README.en.md`: equivalent Italian and English introductions.
- `.agents/skills/`: selected reusable workflows copied with the owner's approval.

The application uses Supabase PostgreSQL, FastAPI REST APIs, and a responsive dashboard
in Italian and English. It supports authenticated administrators and readers, invitations,
source proposals, catalog management, RSS/Atom collection, and manual refresh.
Personal subscriptions and read states are separate from the shared catalog.
Readers and administrators can follow all catalog sources or remove all their subscriptions.
Shared Gemini digests have an administrator-only panel for token usage, estimated costs,
and prudential budget reservations. Reader usage summaries are also administrator-only.

Implemented features are not necessarily deployed. Check the release status separately.
See [architecture](docs/architecture.md), [AI digests](docs/ai-briefs.md), and
[deployment](docs/deployment.md) for behavior and publication requirements.

## Working conventions

- Inspect Git status and applicable instructions before changes. Preserve existing work.
- Implement only the phase or task authorized by the user. Stop after its checks and summary.
- Do not implement future integrations merely to prepare for them.
- Keep code and identifiers in English. Preserve each document's language.
- Update both README versions when their shared content changes.
- Keep READMEs focused on the product. Put database revision numbers and release-specific instructions in `docs/`.
- Distinguish available features from planned features in documentation and UI.
- Keep agent work logs, investigation notes, trial history, and release-specific reports in `docs/agent-notes/`.
  The versioned `.gitignore` excludes this local directory in every checkout.
  Do not put secrets there. Update existing notes rather than creating a report for each turn.
- Keep reusable product, architecture, setup, security, and operating requirements in tracked `docs/` files.
  Prefer updating an existing guide. Tracked files must not depend on excluded agent notes.
- Keep secrets, databases, virtual environments, build artifacts, and personal paths out of Git.
- Use environment configuration where needed. Never put secrets in `VITE_*` variables.
- Keep development servers on loopback. Public deployments and authentication changes require explicit task authorization.
- Treat feed URLs and content as untrusted. Never render unsanitized external HTML.
- Use one backend worker. The collector and source changes share an in-process lock.
- Keep individual and bulk subscription changes scoped to the authenticated user.
  Preserve read states when subscriptions change. Serialize competing changes with the existing per-user transaction lock.
- Read Gemini statistics from stored records. Do not call the provider to display or refresh the panel.
  Keep unavailable consumption distinct from zero, and estimated costs distinct from reservations and billed charges.
  Preserve content-free usage history when saved editions expire. Protect administrative statistics in both the UI and API.
- Keep HTTP fetches in the guarded downloader. Pass only downloaded bytes to feedparser.
- Add dependencies only for current requirements. Keep dependency definitions and locks consistent.
- Change database schemas through Alembic revisions. Do not run `create_all()` or migrations at API startup.
- After a migration is committed and shared, add a new revision instead of rewriting it.
- Use timezone-aware datetimes with the models. Database timestamps store UTC.
- The project uses the MIT License. Preserve copyright and license notices.
- Do not change the license, publish the repository, or change collaborators without explicit authorization.

## Repository investigation

Prefer TokenSave MCP tools when available. Start code exploration with
`tokensave_context`, use `tokensave_search` for symbols or literal text, and check
`tokensave_status` before relying on the graph. Use callers, callees, impact, node,
files, and affected-file queries when applicable. Discover extra tools with
`tokensave_more` (`navigate` or `git`).

Use `tokensave_read` for bounded source reads and maps. Use the editing harness's
file reader for files you are about to edit. Use regular searches for regexes,
unscanned files, non-code tasks, and paths outside an indexed project.

If the project has no index or a tool is unavailable, disclose the limitation and
use read-only filesystem inspection. Do not require TokenSave for contributors.
Sync an existing index only when requested or when the task modifies this repository.
For other initialized projects, pass an absolute `graph_root`. Use branch tools
for other branches of the served project. Before a SQL fallback, locate `db_file`
in `.tokensave/branch-meta.json`, or use `.tokensave/tokensave.db` if metadata is absent.
Report native tool gaps without including private code in any suggested issue.

## Selected skills

Read a skill before applying it. These files are a portable project reference;
automatic discovery depends on the agent. They do not override user instructions.

- [efficient-repo-analysis](.agents/skills/efficient-repo-analysis/SKILL.md): architecture discovery and unfamiliar code.
- [debugging](.agents/skills/debugging/SKILL.md): observed failures and reproducible defects.
- [implementation-review](.agents/skills/implementation-review/SKILL.md): review a specified diff or implementation.
- [security-review](.agents/skills/security-review/SKILL.md): review concrete security boundaries, especially external feeds.
- [ste-documentation](.agents/skills/ste-documentation/SKILL.md): English technical documentation, without claiming certified compliance.
- [frontend-design](.agents/skills/frontend-design/SKILL.md): visual direction and implementation, following the selected editorial design.
- [supabase-postgres-best-practices](.agents/skills/supabase-postgres-best-practices/SKILL.md): PostgreSQL schema, migrations, queries, connection management, privileges, and RLS guidance.
- `web-design-guidelines`: optional local UI review skill in `.agents/skills/web-design-guidelines/`; excluded from Git. Installation details are in the provenance document.

For UI work, preserve Italian sentence case and the existing API behavior. Review
guidelines are a checklist, not authorization to add libraries, URL state, new
business behavior, or unrelated features. Keep the fonts local and preserve their licenses.

Source revision and adoption limits are in [skill provenance](.agents/PROVENANCE.md).

Read the PostgreSQL skill before PostgreSQL database work. Apply only guidance
relevant to the approved phase; keep SQLAlchemy and Alembic as the project's
database tools. Installing a skill does not authorize cloud changes or migrations.

## Verification

Use the commands in [the development guide](docs/development.md).
Backend checks are pytest, Ruff lint, and Ruff format checks. Database tests must
apply real Alembic migrations to disposable local PostgreSQL databases. Frontend checks are
ESLint, TypeScript, Vitest/Testing Library, Prettier, and a production build.
Test user-visible behavior with mocked HTTP, not implementation details or snapshots.

Run focused checks for the change. Report actual results and any checks not run.
Do not infer passing tests from source inspection. Keep tests independent of live
news services and Gemini. Use fixtures and mocked HTTP for collection and AI tests.

## Git workflow

- Work directly on `main` for now, as requested by the owner. Create other branches only when requested.
- Do not create commits or push without explicit authorization for that action.
- Do not force-push or overwrite history.
- A push to `main` runs CI checks, not a deployment. Releases require a separate manual action.
  Use **Release full** for changes to the backend, database, or frontend API requirements.
  This workflow applies migrations and reviewed grants, deploys Render, and then publishes the frontend.
  Use **Release frontend only** only when all pending frontend changes work with the deployed API.
- Before stopping, report completed scope, checks, deviations, and Git status when relevant.
- Propose a commit message only when the change is ready for the owner's push, not after every response.
- Use English commit messages in the form `<type>: <emoji> - <summary>`.
- Use `feat: 🎉 - ...` for initialization, `feat: ✨ - ...` for features, `fix: 🐛 - ...` for fixes,
  `refactor: 📦 - ...` for refactors, `docs: 📝 - ...` for documentation, and `chore: 🔧 - ...` for tooling.

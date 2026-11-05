# Project instructions

## Project context

Tech News Radar is a personal news reader for technology, AI, software development,
and economics. Keep it simple, readable, and suitable for future collaboration.

- `frontend/`: React, TypeScript, Vite, and Tailwind CSS.
- `backend/`: FastAPI, configuration, and backend tests.
- `docs/`: local development instructions and architecture decisions.
- `README.md` and `README.en.md`: equivalent Italian and English introductions.
- `.agents/skills/`: selected reusable workflows copied with the owner's approval.

The current phase provides a scaffold and a health endpoint. SQLite persistence,
RSS collection, source management, and the dashboard belong to later phases.
See [architecture](docs/architecture.md) for the intended scope.

## Working conventions

- Inspect Git status and applicable instructions before changes. Preserve existing work.
- Implement only the phase or task authorized by the user. Stop after its checks and summary.
- Do not implement future integrations merely to prepare for them.
- Keep code and identifiers in English. Preserve each document's language.
- Update both README versions when their shared content changes.
- Distinguish available features from planned features in documentation and UI.
- Keep secrets, databases, virtual environments, build artifacts, and personal paths out of Git.
- Use environment configuration where needed. Never put secrets in `VITE_*` variables.
- Keep development servers on loopback. Public deployment and authentication need a separate task.
- Treat feed URLs and content as untrusted. Never render unsanitized external HTML.
- Add dependencies only for current requirements. Keep dependency definitions and locks consistent.
- Do not add a license, publish the repository, or change collaborators without explicit authorization.

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

Source revision and adoption limits are in [skill provenance](docs/agent-skills.md).

## Verification

Use the commands in [the development guide](docs/development.md).
Backend checks are pytest, Ruff lint, and Ruff format checks. Frontend checks are
ESLint, TypeScript, and a production build. Add behavioral frontend tests when
interactive features arrive, rather than snapshot tests for static placeholder text.

Run focused checks for the change. Report actual results and any checks not run.
Do not infer passing tests from source inspection. Keep tests independent of live
news services. Use fixtures and mocked HTTP for future collection tests.

## Git workflow

- Use `main` as the primary branch. After the initial commit, prefer short-lived `feat/...` or `fix/...` branches.
- Do not create commits or push without explicit authorization for that action.
- Do not force-push or overwrite history.
- Before stopping, report completed scope, checks, deviations, Git status, and a proposed commit message.
- Use English commit messages in the form `<type>: <emoji> - <summary>`.
- Use `feat: 🎉 - ...` for initialization, `feat: ✨ - ...` for features, `fix: 🐛 - ...` for fixes,
  `refactor: 📦 - ...` for refactors, `docs: 📝 - ...` for documentation, and `chore: 🔧 - ...` for tooling.

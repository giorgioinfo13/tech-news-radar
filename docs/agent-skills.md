# Agent skill provenance

The owner authorized the import of selected skills from the independent
`agent-skills` collection on 2026-11-05.

- Source revision: `6b1835126241a0bb4737d56bab5b90708dfed43b`.
- Source directories: `skills/efficient-repo-analysis`, `skills/debugging`,
  `skills/implementation-review`, `skills/security-review`, and `skills/ste-documentation`.
- Destination: `.agents/skills/`, with the same directory names.
- Skill files retain their original content and provenance metadata.
- The root `AGENTS.md` adapts `templates/project/AGENTS.md` to this project.
  The collection's maintenance instructions do not govern this repository.

These are local copies. No package installation, external service, symlink, or
access to the original collection is required. Changes here do not change the
source collection. Review future imports explicitly rather than synchronizing automatically.

At the imported revision, the collection had no repository-wide open-source license.
The owner selected the [MIT License](../LICENSE) for Tech News Radar on 2026-11-05,
including these copies of the owner's skills. This choice does not change the
license status of the independent source collection. Preserve the provenance metadata
and any applicable third-party notices in future imports. No third-party application
source from the architectural reference projects is included.

The skills are available through explicit links in `AGENTS.md`. Automatic discovery
and compatibility with every agent are not verified. TokenSave is optional for
contributors and is not initialized by this scaffold.

The documentation uses the general STE writing guidance. The official FAQ returned
HTTP 403 during setup. No full ASD-STE100 dictionary or compliance audit was performed.

## Frontend design skills

The owner authorized these project-local installations on 2026-11-05:

| Skill | Source revision | Distribution |
| --- | --- | --- |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills/tree/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design), `ca45fc496a3436251f191354091d557da31c15b5` | Included unchanged with its Apache 2.0 `LICENSE.txt` |
| `web-design-guidelines` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/web-design-guidelines), `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62` | Local only, excluded from Git because no explicit license was found in the skill or repository root |

The Codex skill installer copied only these directories into `.agents/skills/`.
No global skill installation, npm dependency, or automatic synchronization was added.
The skill files were read directly for this task. Discovery is available on the next
Codex turn. A clone contains the Anthropic skill but not the optional Vercel copy.

The owner's proposed `npx skills add` commands are an alternative installer, not a
runtime requirement. Use the specific `--skill` and `-a codex` selectors, without
`--global`, for a project installation. Review upstream licensing before redistributing
the Vercel skill. Its review fetches current guidance from the URL in its `SKILL.md`.

The design reference is the approved editorial direction: cool neutral surfaces,
blue actions, Source Serif 4 article titles, and Source Sans 3 controls. Vercel's
review checklist does not override Italian copy, scope, or application behavior.

## PostgreSQL skill

The owner authorized a project-local Supabase skill installation on 2026-11-06.

- Skill: `supabase-postgres-best-practices`, metadata version `1.1.1`.
- Source: [supabase/agent-skills](https://github.com/supabase/agent-skills/tree/c9be0e931b7930f7d02126d04774d904c381e7d7/skills/supabase-postgres-best-practices).
- Source revision: `c9be0e931b7930f7d02126d04774d904c381e7d7`.
- Destination: `.agents/skills/supabase-postgres-best-practices/`.
- Distribution: unchanged skill directory, including its references and changelog.
  The upstream root MIT `LICENSE` is included in the destination directory to
  preserve the Supabase copyright notice.

The Codex skill installer was used instead of `npx skills add`, with an explicit
revision, skill path, and project destination. No npm dependency, global skill,
Supabase CLI, MCP connection, or cloud configuration was installed. The separate
general `supabase` skill was inspected but not installed; it can be evaluated for
the authentication phase.

Use the installed skill for the approved PostgreSQL migration and subsequent
schema, query, connection, and RLS work. It does not replace SQLAlchemy or Alembic,
require advanced database features, or authorize remote operations. Read the
relevant reference files for each task and verify version-sensitive advice against
current official documentation. Future upstream updates require explicit review.

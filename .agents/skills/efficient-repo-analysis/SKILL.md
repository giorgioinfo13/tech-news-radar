---
name: efficient-repo-analysis
description: Investigate a large or unfamiliar repository with a small evidence set. Use for architecture discovery, questions across files, feature location, or implementation planning. Skip a known-file edit or a simple exact lookup.
metadata:
  source: "Local .agents/skills/efficient-repo-analysis/SKILL.md, imported at the user's request on 2026-11-05. The source was untracked, with no upstream URL or commit reference."
  source-sha256: "7f28c9180c97dbad56fef8088579c31f4b89edcdfcaf8f0bedae0bdfd80e1ea5"
---

# Efficient repository analysis

Find the smallest evidence set that answers the question before you read implementation bodies.
Use the destination project's discovery policy. This skill does not make a graph tool mandatory.

## Workflow

1. Identify the concrete question, expected output, and likely subsystem.
   Do not inventory the entire repository unless the task requires it.
2. Start at the repository root unless the task specifies a narrower scope.
   Include relevant applications and packages. A selected branch defines the code version, not the repository boundary.
3. Identify candidate entry points, related symbols, tests, and configuration.
   Treat search matches as leads until source evidence supports them.
4. If you use an index, confirm its project, branch, and freshness before relying on it.
   Obey the project's policy for index updates and source inspection.
   If a mandatory tool is unavailable, report the missing prerequisite.
   Otherwise, use available file and symbol searches when graph tools cannot answer the question.
5. Read maps, signatures, diffs, or bounded line ranges before entire files.
   Trace callers, imports, and state flow only as far as the question requires.
6. Find an existing implementation of similar behavior before proposing a new pattern.
   Consult architecture documentation for relevant boundaries.
   Use history or blame only when current code does not explain intent.
7. Expand the investigation one layer at a time.
   Stop when the evidence answers the question. Identify gaps instead of expanding the scope without a reason.

## Output

Summarize the relevant path, evidence locations, constraints, and unresolved facts.
For implementation planning, include likely file changes and targeted verification.
Keep source quotations short. Do not implement changes for a discovery-only request.

## Compatibility

Repository read access is sufficient. Use graph tools, symbol tools, or targeted text searches as available and permitted.
No agent-specific service is required by this skill.
Manual exercise in Codex on 2026-11-05: traced a synthetic route through a service to its data store using source inspection.
Automatic discovery and other agents remain untested.

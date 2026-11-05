---
name: implementation-review
description: Review implementations, working-tree changes, branches, commits, or pull-request diffs for defects and regressions. Use for requested code review, self-review, or pre-merge assessment. Do not activate for ordinary implementation work or diagnosis without a review target.
metadata:
  source: "Local .agents/skills/implementation-review/SKILL.md, imported at the user's request on 2026-11-05. The source was untracked, with no upstream URL or commit reference."
  source-sha256: "30e7823167be09df1e1b87b7b4d2c7c1e0bda55b31d260aff54fbb371f9c42cc"
---

# Implementation review

Review the specified change. Expand into surrounding code only when necessary to assess its behavior.
Keep the review read-only unless the user requests fixes.

## Workflow

1. Identify the review target and comparison base without changing branches or files.
   Inspect status, changed-file names, diff statistics, and the diff.
   If no comparison base exists, state the scope of the available implementation review.
2. Derive intended behavior from the request, relevant tests, and documentation.
   State when the intent is unclear.
3. For each risky change, inspect the smallest relevant caller, callee, state, or test path.
   Use available graph tools or direct source inspection under the project's discovery policy.
4. Examine correctness, state mappings, boundaries, error handling, cleanup, concurrency, timing, and compatibility.
   Report duplicated logic or architecture issues only when they have a concrete effect on the change.
5. Trace sensitive values and external commands through their relevant paths.
   Do not infer protocol or runtime behavior from names alone.
6. Separate confirmed defects from questions and optional improvements.
   For each finding, give a failure scenario, supporting evidence, affected location, and the smallest reasonable correction.
7. Suggest targeted tests for uncovered behavior.
   Run checks only within the user's authorization and the project's verification policy.
   Report checks that did not run and any resulting uncertainty.

## Output

Report findings first, ordered by severity, with precise file and line references.
Include the practical effect of each defect. If there are no supported findings, say so.
Keep residual test gaps and incomplete traces separate from confirmed defects.

## Compatibility

Use repository and diff access available in the destination environment.
Tokensave, a hosting provider, and a specific test framework are not required by this skill.
Manual exercise in Codex on 2026-11-05: identified a pagination regression in a synthetic diff and reproduced its nonzero-offset failure.
Automatic discovery and other agents remain untested.

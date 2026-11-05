---
name: debugging
description: Diagnose defects, crashes, failing tests, build errors, and unexpected runtime behavior through reproduction and testable hypotheses. Use for debugging and root-cause analysis. Do not use for a static review without an observed failure.
metadata:
  source: "Local .agents/skills/debugging/SKILL.md, imported at the user's request on 2026-11-05. The source was untracked, with no upstream URL or commit reference."
  source-sha256: "215d425dc0acb18038dd7482257b16cd733819b5633ffc342dcffee956ad37be"
---

# Debugging

Find the first incorrect state before you change code.
Keep experiments within the user's authorization and the project's verification policy.
If reproduction is unsafe or unavailable, state which evidence you can use instead.

## Workflow

1. Record expected behavior, observed behavior, the exact failure, and the environment.
   Determine whether the failure occurs consistently.
2. Reproduce the failure with the smallest applicable case, when permitted.
   Read the error and relevant logs. Identify the smallest execution path that can explain it.
3. Use exact searches for known errors and identifiers.
   Use available graph tools or source inspection for relationships across files, under the project's discovery policy.
   Consult recent changes only when a regression or unclear intent makes them relevant.
4. Select one hypothesis that an experiment can confirm or reject.
   State the expected observation before the experiment. Run the smallest permitted experiment and record the result.
5. Trace the symptom back to the earliest incorrect state.
   Prefer a correction to the cause over a guard that only hides the symptom.
6. For a diagnosis-only request, report the supported cause without changing implementation files.
   If a fix is authorized, change only the necessary area.
7. If a fix changes behavior, add or update a focused regression check when feasible.
   Repeat the reproduction and applicable adjacent checks when permitted.
   If verification cannot run, report the remaining uncertainty. Do not claim resolution from inspection alone.

## Output

Report the cause, evidence, rejected hypotheses, changed files, and verification results.
Separate observed facts from assumptions. Remove secrets and sensitive payloads from logs and output.

## Compatibility

Use the project's existing tools. This skill does not require Tokensave or a specific test runner.
Execution can be limited by the destination project's policies.
Manual exercise in Codex on 2026-11-05: reproduced an empty-input failure and stopped after diagnosis, without a fix.
This was a synthetic Python case. Automatic discovery and other agents remain untested.

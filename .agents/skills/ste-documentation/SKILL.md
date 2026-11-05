---
name: ste-documentation
description: Write or review English technical documentation with ASD-STE100 Issue 9 as the reference. Use for setup, configuration, firmware update, and troubleshooting guides. Do not use for unrelated coding or ordinary conversation.
metadata:
  source: "Local .agents/skills/ste-documentation/SKILL.md, imported at the user's request on 2026-11-05. The source was untracked, with no upstream URL or commit reference."
  source-sha256: "4f83b590dc7dcd072ab8c76b2cb3a1567574c5ae67141d5716a10fe50a835e7c"
---

# STE technical documentation

Use [ASD-STE100 Issue 9 (January 2025)](https://www.asd-ste100.org/) as the
reference for Simplified Technical English (STE). Keep the technical meaning when you simplify the wording.
This skill supports STE-aligned writing. It does not certify compliance.

## Scope and reference

- Apply the skill to new or modified English technical prose. Keep the
  language of documents written in other languages. Do not impose STE on normal
  chat unless requested.
- Use the official Issue 9 rules and controlled dictionary when available.
  The [official FAQ](https://www.asd-ste100.org/STE_faq.html) explains their scope.
  Use the [official standard](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf)
  for detailed review. If web access fails, use a copy supplied by the user.
  Do not copy the standard into the repository.
- If the full reference is unavailable, apply the general principles below.
  Report which rules or vocabulary checks remain unverified. Do not invent rule
  numbers, dictionary entries, approved meanings, or parts of speech.
- Call the result STE-aligned unless a review against the applicable rules and
  dictionary supports a stronger claim. Before you make a compliance claim, record
  the issue, reviewed scope, and verification method.

## Issue 9 checks

These checks restate selected rules for this workflow. They do not replace the standard.

- Classify each passage as procedural or descriptive before you apply sentence limits.
  Procedure sentences have a 20-word limit. Descriptive sentences and informational notes have a 25-word limit (rules 5.1 and 6.3).
  Count words with the conventions in rules 8.4-8.7, including quoted text, identifiers, and parentheses.
- Use a command for each instruction. Keep separate actions in separate sentences unless they occur together (rules 5.2-5.3).
  Put a prerequisite condition before the command (rule 5.4). Notes contain information, not instructions (rule 5.5).
- Give each descriptive paragraph one topic and no more than six sentences (rules 6.5-6.6).
  Do not use semicolons in prose (rule 8.1). Keep semicolons in code and other fixed literals unchanged.
- Examine each dictionary entry for the permitted part of speech, meaning, and word form (rules 1.2-1.4).
  A familiar word is not automatically permitted in every context.
- For software terms, apply the technical-noun and technical-verb criteria in rules 1.5-1.13.
  Record the term, its meaning, and its category when the exception is necessary.
  Do not treat all software vocabulary as exempt. Prefer a dictionary word when it gives the same meaning.
- Examine verb forms and voice under rules 3.2-3.6.
  Do not use perfect or progressive tenses. Use active voice for procedures.
  In descriptive text, passive voice is permitted only when the person or thing that does the action is unknown.
  Examine words with an -ing ending under rule 3.5, including the technical-noun and dictionary exceptions.
- Use American English spelling unless an official requirement specifies another form (rule 1.14).
  Keep product names, identifiers, and quoted text unchanged.

## Writing and review

1. Identify the audience, document language, and requested scope. Read the relevant
   agent instructions and the project's terminology guide, if one exists.
   If there is no guide, use terms consistently with the existing documentation.
   Keep existing headings, links, diagrams, and clear passages.
2. Compare technical claims with source files, configuration, tests, or protocol references.
   Obey the repository's discovery policy. Mark unknowns.
   Do not invent missing behavior, prerequisites, timing, or recovery steps.
3. Use short sentences with one topic. Prefer active voice and direct instructions.
   If a pronoun or passive sentence is ambiguous, name the actor, component, or
   condition. Use the same term for the same concept. Expand unfamiliar abbreviations.
4. Give each procedural sentence one instruction unless actions occur together. Put prerequisites and conditions
   before the action they control. Separate instructions from explanations and
   expected results. Do not split actions that must occur together into a false sequence.
5. For installation and configuration, state the working directory, platform,
   required inputs, and expected result when these are known. For firmware updates,
   keep device applicability, version constraints, sequence, timing, retries,
   warnings, and recovery limits exactly. For troubleshooting, distinguish the
   observed symptom, diagnostic check, possible cause, and supported corrective action.
   Do not run documented commands or communicate with devices just to review prose.
6. Keep code blocks, commands, paths, API names, identifiers, configuration
   keys, UI labels, placeholders, and protocol terms. STE vocabulary restrictions
   do not apply to source code or machine syntax. When these literals must remain
   unchanged, report incorrect examples separately.
7. Keep normative force, conditions, exceptions, and security requirements unchanged.
   Do not substitute `must`, `shall`, `should`, `may`, or `can` merely for style.
   Do not automatically rewrite legal documents, historical changelogs, generated
   files, or third-party documentation. Do not edit runtime code for a writing task.

## Final review

- Compare the diff with the original for omitted facts, changed requirements,
  ambiguous references, and inconsistent terminology. Confirm literal examples
  and commands are unchanged unless their correction was explicitly authorized.
- Do a check of local Markdown links and references where practical.
  Use existing documentation validators when authorized. Do not add a dependency or framework.
  Obey the repository's policy for checks, generation commands, and builds.
- Report changed files, technical evidence, checks performed, documents not
  reviewed, and remaining uncertainty. A readable document or a passing linter
  alone does not establish ASD-STE100 compliance.

## Compatibility

No agent-specific tool or runtime is necessary. Codex used these instructions for a documentation review on 2026-11-05.
No tests were done with Claude Code or other agents.

The official links returned HTTP 403 during the first review. A later review used the user's local Issue 9 PDF.
That review examined selected writing rules and dictionary entries. It did not include an exhaustive vocabulary audit or approve a project glossary.
The result remains STE-aligned, with no claim of full compliance. The standard is not included in this repository.

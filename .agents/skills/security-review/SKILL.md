---
name: security-review
description: Review a specified change or code path for application security risks at trust boundaries. Use when security is requested or a concrete risk makes it relevant. Do not turn routine edits into a full security audit.
metadata:
  source: "Local .agents/skills/security-review/SKILL.md, imported at the user's request on 2026-11-05. The source was untracked, with no upstream URL or commit reference."
  source-sha256: "e078764709f6083a3c18150ffc2e13829861e692311002814a30fddb1f5d3e42"
---

# Security review

Define the review scope before searching broadly.
Identify assets, actors, trust boundaries, attacker-controlled inputs, sensitive outputs, and the exact flow under review.
Keep the review read-only unless the user requests changes or active checks.

## Review

Trace relevant data from source to sink. Establish the existing controls before you report a vulnerability.
Examine only categories that apply to the target:

- Input validation, injection, unsafe deserialization, and malformed protocol data.
- Authentication, authorization, privilege boundaries, replay, and insecure defaults.
- Secrets, credentials, logging, identifiers, and sensitive storage.
- Cryptographic purpose, key and nonce handling, randomness, and custom cryptography.
- Transport security, endpoint validation, certificate handling, and network or device communication.
- Dependency and supply-chain risks when dependencies or build configuration change.

Use current authoritative advisories for claims about dependency vulnerabilities.
If advisory access or version evidence is unavailable, state the limit instead of asserting a known vulnerability.
Do not contact external systems or real devices merely to demonstrate a finding without explicit authorization.
Never include secrets or raw sensitive payloads in the report.

## Output

Report vulnerabilities only when evidence supports a reachable path and a concrete effect.
For each finding, give severity, confidence, evidence, the attack or failure scenario, the affected location, and minimal remediation.
Label incomplete traces as `needs verification`.
Keep optional hardening separate from vulnerabilities. Include the checks performed and areas outside the reviewed scope.

## Compatibility

Source review requires read access to the relevant code and configuration.
Current dependency claims can require advisory access. No scanner or agent-specific service is required by this skill.
Manual exercise in Codex on 2026-11-05: identified a missing ownership check in a synthetic report-retrieval path.
This was a source review, without external access or exploit execution. Automatic discovery and other agents remain untested.

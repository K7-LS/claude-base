# LLM-base rework

Date: 2026-07-26

## Scope

- investigate extreme token usage with real local usage evidence;
- separate Anthropic account-risk facts from hypotheses;
- replace the shared pseudo-universal layer with native Claude/Codex/OpenCode
  targets;
- remove Kimi as a target;
- change sync to hub-to-consumer only;
- adapt Foundation installer last;
- keep full release fail-closed.

## Implemented

- compact `core/AGENTS.core.md` plus three target layers;
- `base-manifest.json` and `context-budget.json`;
- explicit active set: one compact auditor, zero active skills per target;
- OpenCode native config and launcher with Claude compatibility imports
  disabled;
- safe `base_cli.py` render/verify/doctor and `token_audit.py`;
- minimal shared Claude settings and one-time retirement of formerly forced
  expensive keys;
- consumer no-push guard and local SessionEnd no-op;
- removal of reverse feedback/token scripts;
- migration and risk audit documents;
- Foundation schema v2 with three targets, one-way sync policy, target-isolated
  transactions/state/rollback, and rendered-file mapping.

## Evidence

Real transcript audit:

- 168 unique model requests;
- 380 duplicate usage records removed;
- 97,408,894 processed context tokens;
- 97,998,788 processed tokens including output;
- median 614,212, p95 933,333, maximum 979,985 per request.

Static target budgets:

- Claude 1,976;
- Codex 1,901;
- OpenCode 1,957;
- limit 3,000 each.

Interactive verification completed against the then-current worktrees:

- base Python suite: 229/229 PASS;
- one-way sync test: PASS in PowerShell 7 and 5.1;
- auto-push staged-index safety, context governor, and tool-gate tests: PASS
  in PowerShell 7 and 5.1;
- Foundation installer: 115/115 PASS in PowerShell 7 and 115/115 PASS in
  Windows PowerShell 5.1;
- schema validation and added/untracked secret-signature scans: PASS;
- OpenCode adapter validates against the current official config schema;
- independent review reproduced three release-gate defects during
  implementation: install/rollback interruption progress, unbound declared
  source identity, and unenforced rendered map. All three now have negative
  regression tests and fail-closed fixes;
- fresh immutable-commit acceptance and final independent verdict remain
  required before handoff;
- full release: NOT PASS.

The interactive test counts above are development observations, not retained
immutable release evidence. Only a post-commit Foundation acceptance attempt
bound to the exact installer commit can satisfy that evidence gate.

## Account-risk conclusion

Russian language is not established as a ban trigger. Stronger observed risks
are unsupported geography, unusual high-volume agentic activity,
`bypassPermissions`, external cloud parsing and secret-like values in shell
payloads. Only Anthropic Safeguards can state the exact hold cause.

## Boundaries and next gates

- No live client home, auth, model, subscription or employee device was
  changed.
- Direct build-repository clone inside a native home remains legacy and is not
  token-safe.
- No production package or employee ZIP was created.
- Required next: final independent verdict, immutable rendered
  source/evidence, separately authorized canary, then matched live token A/B.

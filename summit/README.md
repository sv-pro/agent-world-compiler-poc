# Summit Materials

This directory contains conference-supporting materials for the `agent-world-compiler-poc` repository.

The proposed talk is based on the PoC implemented in this repository and focuses on a practical pipeline:

``` Observe -> Profile -> Manifest -> Enforce ```

The current PoC demonstrates:

- deriving a bounded capability profile from a benign repository-maintenance trace;
- compiling that profile into a World Manifest;
- enforcing deterministic `ALLOW`, `DENY`, and `REQUIRE_APPROVAL` decisions;
- blocking unsafe actions such as secret access, tainted-data exfiltration, out-of-scope remote operations, and trust-violating execution paths.

## Contents

- `CFP_Submission.md` — full CFP-ready draft.
- `cfp/abstract.md` — short and full abstract only.
- `cfp/bio.md` — speaker bio.
- `cfp/learning-objectives.md` — learning objectives.
- `cfp/reviewer-notes.md` — reviewer-facing fit and scope notes.
- `talk/outline.md` — 25–30 minute talk structure.
- `talk/demo-plan.md` — how to present the PoC demo.
- `talk/script-notes.md` — core speaking notes.
- `talk/qa-prep.md` — likely questions and concise answers.
- `slides/slide-outline.md` — planned slide flow.
- `slides/diagrams.md` — diagrams to include.
- `slides/speaker-notes.md` — notes by slide.

## Positioning

This is not a claim to solve agent safety in general.

It is a bounded claim: observed agent execution can be compiled into deterministic runtime boundaries for specific workflows.

## Repository link

- PoC repository: https://github.com/sv-pro/agent-world-compiler-poc

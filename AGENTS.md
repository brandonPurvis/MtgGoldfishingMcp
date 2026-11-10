# MTG Goldfishing

A service that holds the state of agent-played Commander goldfish games. Project vocabulary is defined in `GLOSSARY.md`; use those terms in docs, code and tool descriptions.

## Engineering conventions

These apply to every change. The reasoning is in `docs/high-level-design.md` (tenet *The domain stays pure*) and `docs/intent/application/application-design.md`.

- **Domain-driven.** Model the game in code with the glossary's words. Name types, functions and tests after domain concepts. If a concept has no name yet, add it to `GLOSSARY.md` before using it in code.
- **Ports and adapters.** Dependencies point inward: `adapters → application → domain`. The domain performs no I/O and imports nothing outside itself and the standard library. Ports are defined in `application/ports.py` and speak in domain types.
- **Rules live in the domain.** A rule of play is never implemented in a tool handler, a renderer or a SQL statement.
- **Value objects are immutable** (frozen dataclasses), validate themselves on construction, and compare by value.
- **Refusals are return values.** Errors and failed rule checks are returned, not raised. Exceptions mean a defect.
- **Typed throughout.** Full type hints; the type checker and linter must pass.
- **Tests.** Domain tests use no adapters. Arrange with the builders in `tests/support`. Use the in-memory adapters, not a mocking library, for ports. Name a test for the behavior it protects. One reason to fail per test. Every new adapter runs the port's contract suite.

## LID
- Mode: Full
- Version: 1.4.3

## Linked-Intent Development (MANDATORY)

**Consult the `linked-intent-dev` skill for ALL code changes.** All changes flow through the arrow of intent in one direction:

```
HLD → LLDs → EARS → Tests → Code
```

- **All changes**: consult the `linked-intent-dev` skill if your harness provides it; otherwise read `docs/lid/workflow.md` before making changes, and if it is missing and `## LID` records no decline, offer the user once to add it from https://raw.githubusercontent.com/jszmajda/lid/v1.4.3/plugins/linked-intent-dev/skills/update-lid/references/workflow-doc.md (on decline, add `- Workflow doc: declined` to `## LID`). The workflow in one line: HLD check → LLD → EARS specs → edge audit → failing tests first → code — inspected at each phase.
- **Bug fixes**: walk the arrow like any other change — find where behavior diverged from intent and cascade from there. No short-circuit.

Each phase's output is inspected — by the user or an inspector they name — before the next begins; ambiguous spec readings go back to the user. **Docs carry current intent, written to be read cold** — write each doc as if authored fresh today, from current intent alone: no narration of how it changed, no meaning that needs the conversation that produced it, no rebuttals to questions only a past discussion raised. Rationale, considered alternatives, and constraints a fresh author would independently write stay; record rejected alternatives and why in the LLD's Decisions & Alternatives table, not as asides in body prose.

**Memory vs. intent.** Before saving durable project knowledge to agent or tool memory, test whether it is project *intent* — would a fresh agent, in any tool, next session, need it to build this system correctly? If yes, record it in the arrow (HLD / LLD / EARS / decision doc), which travels and cascades — not in private, per-tool memory, where intent escapes the arrow. Knowledge about the user or how they like to work stays in memory.

### Navigation

| What you need | Where to look |
|---|---|
| High-level design | `docs/high-level-design.md` |
| Design tree (sub-HLDs, LLDs, their specs) | `docs/intent/` — one folder per node |
| EARS specs | beside each design doc as `{node}-specs.md` in the node's folder under `docs/intent/` |
| Decision docs | `docs/decisions/` (project-level) and `docs/intent/<segment>/decisions/` |

### Terminology

- **HLD**: High-Level Design — single project-level doc at `docs/high-level-design.md`.
- **LLD**: Low-Level Design — detailed component design doc in `docs/intent/`. The design layer is a recursive tree: the root is the HLD, leaf LLDs own EARS, and a component deep enough to outgrow one doc becomes a sub-HLD (HLD-shaped, owns no EARS) with children beneath it. "HLD" and "LLD" are roles by position; depth-2 (one HLD over flat leaf LLDs) is the default.
- **EARS**: Easy Approach to Requirements Syntax — structured one-line requirements beside each design doc as `{node}-specs.md` in the node's folder under `docs/intent/`. IDs are path-concatenated — the root-to-leaf path of the owning segment plus a number — so a prefix grep gathers a subtree. Markers: `[x]` implemented, `[ ]` active gap, `[D]` deferred.
- **Arrow**: the unidirectional chain from vision to code (HLD → LLDs → EARS → Tests → Code). Strictly a DAG of intent.
- **Arrow segment**: the territory owned by one leaf LLD — the LLD itself plus the specs, tests, and code that cite its EARS IDs. The boundary is the leaf prefix. Within-segment cascade is free; across-segment cascade pauses.
- **Cascade**: propagating a change downstream through the arrow so adjacent levels stay coherent.

### Code annotations

Annotate code and tests with `@spec` comments citing EARS IDs:

```
# @spec PAY-001, PAY-002
```

Place the annotation at the *entry point of the behavior's implementation graph* — the topmost function or module owning the specified behavior, not every helper. When a behavior spans multiple subsystems, annotate at the entry point in each subsystem. Tests follow the same rule: annotate the test that directly exercises the spec, not every inner assertion.

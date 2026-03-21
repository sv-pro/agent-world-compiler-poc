# Conference Speech Draft

**Title:** From Behavior to Boundaries: Compiling Observed Agent Execution into Least-Privilege Worlds

**Target length:** 10–15 minutes spoken
**Tone:** Technical, conference-appropriate
**Notes to presenter:** Sections marked *[PAUSE]* are natural breath points. Code and YAML snippets are for the slide — read around them, not through them.

---

## Opening

Let me start with a scenario that's become familiar.

You deploy an agent to handle repository maintenance. It reads files, runs tests, stages changes, commits, and pushes. Simple, bounded workflow. You approved it. You trust it.

Three weeks later, someone notices the agent is reading environment variables it has no business touching. It tried to post to an external URL. It pushed to a fork instead of origin. Nobody authorized any of that. Nobody denied it either — because nobody ever defined what the agent was allowed to do.

This is scope creep. And it's not a model alignment problem. It's an authorization problem. The agent's effective capability was never defined. It evolved opportunistically, through discovered tools, accumulated approvals, and task variability. And when it overstepped, there was no boundary to stop it.

*[PAUSE]*

Today I want to show you a pattern for fixing that. Not through reactive filtering. Not through prompt guardrails. Through something more direct: deriving an explicit, minimal, reproducible execution boundary from the agent's own observed behavior.

---

## The Problem with How We Write Policy Today

When teams do define agent permissions, they usually write them by hand. They think about the workflow, enumerate the tools that seem relevant, and write a configuration.

This is better than nothing. But it has a structural weakness: it is based on what the author imagined the workflow requires, not what the workflow actually does.

Hand-written policy is an opinion. It over-permits things the author thought might be needed. It sometimes under-permits things that are actually required. And when the workflow evolves, the policy drifts.

There is a better starting point available: the execution trace.

Your agent already produces one. Every tool call, every resource touch, every dependency between steps — it is all observable. The question is whether you use it.

---

## The Proposal

The pattern I want to walk through is this:

```
Observe → Profile → Manifest → Enforce
```

Four stages. Each has a clear input and a clear output.

**Observe**: record agent execution as a structured trace. Each step captures the tool invoked, the action type, the resource URI, the input sources the step drew on, and the steps it depends on.

**Profile**: run the trace through a profiler. The profiler reads the benign, untainted steps and derives a minimal capability profile: the set of (tool, action, resource-prefix) combinations that safe execution actually required.

**Compile**: run the profile through a manifest compiler. The compiler emits a declarative YAML document — the World Manifest — that encodes allowed actions, denied actions, trust requirements, and approval gates.

**Enforce**: evaluate any incoming step against the manifest. The engine returns one of three deterministic decisions: `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`.

The trace is the first concrete runtime artifact. Everything else is derived from it.

*[PAUSE]*

---

## The Bootstrap Trust Model

Before I go further, I need to explain how taint gets into the system.

When an agent step executes, it draws on input sources — the data it is using to make decisions. These sources have different provenance characteristics. Content from the local repository is under your control. An environment variable might contain a secret that was set by a human. LLM output is not under your control at all; it is generated text.

The system starts from a built-in assumption about what those source types mean for trust. We call this the **bootstrap trust model**:

```
repo_local  → trusted
environment → untrusted
llm_output  → untrusted
tool_output → conditional
```

This is not something the user writes. It is the system's default starting point, derived from reasonable security assumptions about where data comes from.

The manifest inherits this mapping in its `input_trust` block. It can be refined per-deployment, but the bootstrap defaults apply unless explicitly overridden.

---

## Taint Derivation

Now here is where it gets concrete.

Each step in the trace declares its `input_sources`. The taint module looks up each source in the trust map. If any source resolves to `untrusted` or `conditional`, the step is source-tainted. That is it. No heuristics. No model judgment.

> Taint is a deterministic function of provenance and flow.

And it propagates. Steps declare `depends_on` — the step IDs whose outputs feed into them. If any step in that dependency chain is tainted, the current step inherits that taint.

Here is a concrete example. Step 1 reads a `SECRET_TOKEN` from the environment — untrusted source. Step 2 posts to an external URL and declares `depends_on: [step-001]`. Even if step 2's own input sources look clean, it inherits taint from step 1. The taint travels through the execution graph.

The enforcement engine then applies the core invariant:

> Tainted data cannot trigger an external side effect.

A tainted step that tries to reach an external resource gets `DENY`, regardless of what the action looks like in isolation.

*[PAUSE]*

---

## The Safe Compression Principle

One more conceptual point before the demo, because it matters for correctness.

The profiler and compiler may simplify what they observe. Multiple specific resource URIs might collapse into a prefix pattern. That is acceptable — precision can be sacrificed for practicality.

But one constraint is absolute:

> You can lose precision, but you cannot add new capabilities.

The manifest may compress observed behavior, but it must never introduce capabilities not present in the safe trace.

In practice: tainted steps never widen the allowed set. The compiler only emits allowed-action entries that correspond to tools and actions observed in the benign, untainted trace. The catch-all `undefined_actions: deny` constraint is always present.

This is the safety invariant of the compilation step. If it is violated, the manifest is derived incorrectly.

---

## The Demo

Let me walk through what this looks like with the PoC.

*[Show benign trace]*

We have a simple repository maintenance trace: read source files, run tests, stage, commit, push to origin. Five steps. All input sources are `repo_local`. Derived taint is false throughout — everything flows from trusted sources.

*[Show profiler output]*

The profiler produces a capability profile: `fs_read`, `shell_exec`, `git_add`, `git_commit`, `git_push` are the allowed tools. Resources are in the `repo://local/*` and `repo://remote/origin/*` namespaces.

*[Show manifest]*

The manifest compiler produces the World Manifest. It encodes the allowed actions, marks `git_push` to remote as `REQUIRE_APPROVAL`, and explicitly denies `http_post` and `env_read` — those were not in the benign trace, so they are not in the manifest, and the catch-all denies them anyway.

*[Show benign evaluation]*

Evaluate the benign trace against this manifest. `git_commit` to local — `ALLOW`. `git_push` to origin — `REQUIRE_APPROVAL`. Everything within scope passes. The remote push surfaces for human review, as expected.

*[Show unsafe trace]*

Now the unsafe trace. Step 1: read `SECRET_TOKEN` from environment. Step 2: post to attacker.example.com, depends on step 1. Step 3: push to fork, depends on step 1. Step 4: execute LLM-constructed shell command, depends on step 1.

*[Show unsafe evaluation]*

Step 1: `env_read` — `DENY`. Explicitly denied; not in the declared workflow.
Step 2: `http_post` to external URL — `DENY`. Tainted data cannot trigger external resource.
Step 3: `git_push` to unauthorized remote — `DENY`. Tainted and resource outside permitted patterns.
Step 4: `shell_exec` from LLM output — `DENY`. Tainted.

Every unsafe action is caught. Each for a clear, auditable reason.

*[PAUSE]*

---

## Why This Matters

Let me step back and state the value plainly.

The pattern bridges runtime observation and design-time policy. You observe real execution. You derive a profile from what actually happened. You compile a manifest from that profile. The resulting policy is evidence-backed, not guessed.

The resulting boundary is:
- **reproducible** — anyone can re-derive it from the same trace
- **reviewable** — the manifest is a human-readable YAML document; an operator can inspect and approve it
- **minimal by construction** — it covers what was observed, nothing more

Compare this to the alternative. A hand-written manifest is an assumption about what the workflow needs. It may be reasonable, but it is still an assumption. A derived manifest is grounded in what the workflow actually did under observed benign conditions.

The value is not just that a manifest exists — it is that it can be derived from evidence rather than guessed.

And once the manifest exists, the enforcement is entirely deterministic. Same manifest plus same step equals same decision, every time. No runtime heuristics. No probabilistic judgments. Undefined actions are denied. Tainted data cannot reach external targets. Sensitive operations surface for human review.

---

## Limitations

I want to be direct about what this PoC does not do.

There is no live orchestration interception. This is a pipeline over stored traces, not a real-time enforcement layer.

There is no OS-level sandboxing. The manifest says `DENY`, but nothing at the OS level enforces that independently.

There is no multi-agent trust. When agents orchestrate other agents, trust propagation across that boundary is a different problem.

The current capability model is intentionally coarse. The trace captures `(tool, action, resource)`, but the profiler and compiler currently collapse some of that structure. Finer-grained action semantics — for example, distinguishing a `write` that appends from one that overwrites — are not represented in the current manifest schema.

This is a PoC for a pattern, not a production platform.

What it does demonstrate — clearly, I think — is that the derivation is possible. Observed execution can be the input. A deterministic boundary can be the output. The pipeline works end-to-end.

*[PAUSE]*

---

## Practical Takeaways

If you are building or operating agent systems today, here is what this pattern suggests:

**Log structured execution.** If your agent framework does not emit structured traces with tool, action, resource, and input provenance, start there. The trace is the foundation.

**Identify bounded workflow modes.** Most agents have recurring patterns — the repository maintenance case, the ticket-triage case, the data-fetch case. Each of those is a candidate for a manifest.

**Derive, then review.** Use observed traces to generate a draft capability profile. Review it. Tighten it. Compile a manifest. That manifest then becomes the policy artifact your team reviews and signs off on.

**Move decisions to design time.** The point of deterministic enforcement is to reduce runtime improvisation. Approval gates that currently happen ad hoc can be made explicit. Actions that are clearly out of scope can be denied unconditionally.

---

## Closing

This PoC does not try to make agent reasoning safe. It makes the executable boundary around agent actions explicit, minimal, and reproducible.

The core idea is simple: agents leave traces. Traces encode what actually happened. From that evidence, you can derive what should be allowed. And from that derivation, you can enforce decisions that are deterministic, auditable, and reviewable by a human engineer.

Scope creep does not have to be an inevitable property of agentic systems. A defined boundary, derived from observed behavior, is achievable with tooling that is not particularly exotic. That is what this PoC demonstrates.

Thank you.

---

*End of speech draft.*

---

## Appendix: Key Lines for Memorization

These ideas should flow naturally in the talk. Use your own wording if needed, but keep the core meaning intact:

- "This PoC does not try to make agent reasoning safe; it makes the executable boundary around agent actions explicit, minimal, and reproducible."
- "Taint is a deterministic function of provenance and flow."
- "You can lose precision, but you cannot add new capabilities."
- "The value is not just that a manifest exists, but that it can be derived from evidence rather than guessed."

## Timing Guide

| Section | Target |
|---|---|
| Opening (scenario + problem framing) | 2 min |
| Problem with hand-written policy | 1.5 min |
| The proposal (four stages) | 2 min |
| Bootstrap trust model | 1.5 min |
| Taint derivation | 2 min |
| Safe compression principle | 1 min |
| Demo walkthrough | 3 min |
| Why this matters | 1.5 min |
| Limitations | 1 min |
| Practical takeaways + closing | 1.5 min |
| **Total** | **~17 min** *(trim demo or limitations section to hit 15)* |

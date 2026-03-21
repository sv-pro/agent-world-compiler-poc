# Abstract

## Title

From Behavior to Boundaries: Compiling Observed Agent Execution into Least-Privilege Worlds

## Alternate Title

Compiling Agent Behavior into Deterministic Security Boundaries

## Track

Secure-by-Design Agentic Applications

## 50-word Abstract

Agentic AI systems often accumulate permissions through scope creep, repeated approvals, and task variability, widening the gap between intended behavior and actual runtime power. This talk presents a practical architecture for turning observed execution into capability profiles, World Manifests, and deterministic enforcement boundaries for safer agentic systems.

## 200-word Abstract

Agentic AI systems expand the security problem beyond prompts into tool use, privilege growth, orchestration, and external side effects across multi-step workflows. Many current defenses still operate after the model has already processed dangerous input, leaving systems exposed to prompt injection, unsafe tool use, and over-privileged execution paths. This talk presents a practical architecture for converting observed agent execution into least-privilege runtime boundaries instead of relying only on reactive guardrails.

The workflow is straightforward: observe execution traces, derive bounded capability profiles, compile them into declarative World Manifests, and enforce deterministic runtime decisions such as ALLOW, DENY, and REQUIRE_APPROVAL. A minimal proof of concept demonstrates this pipeline on a repository-maintenance scenario, showing how benign behavior can be profiled and how unsafe actions such as secret access, tainted-data exfiltration, and out-of-scope remote operations can be blocked or escalated through explicit policy.

The session connects this model to current secure-by-design guidance for agentic applications, least-privilege controls, policy-as-code, runtime enforcement, and scope-creep containment, and closes with practical steps teams can adapt to their own agent platforms.

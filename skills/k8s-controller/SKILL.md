---
name: k8s-controller
description: >-
  Design and implement controller-runtime reconciliation for an already-served
  Kubernetes-style API in a controller-runtime manager. Trigger when the
  user asks to write or rewrite controller logic, reconcile a Kind, add watches
  or finalization, manage owned resources, update status and conditions, or
  register a reconciler. Covers reconcile-contract selection, watches and
  indexes, idempotent convergence, finalizers, status ownership, registration,
  and controller tests. Do not use for API type definitions, apiserver storage,
  component-config schema authoring, or end-to-end tests.
---

# Kubernetes Controller Engineering

Implement a control loop for an API that is already served and has a generated
client. The result is not merely a compiling `Reconcile` method: repeated calls
must converge safely under duplicate events, stale cache reads, optimistic
conflicts, process crashes, partial external success, and deletion.

This skill owns the target repository's controller package (commonly
`internal/controller/**`), its focused tests, watches/indexes, and
controller-manager registration. Component config belongs to
`k8s-controller-config`; API types and validation belong to `k8s-crd-api`;
serving/client generation belongs to `k8s-apiserver-rest`.

## Design model

There is no universal controller skeleton. Select the smallest pattern that
matches the source of truth and side effects:

- observer/status controller;
- owned-resource controller;
- aggregate/scaler controller;
- scheduled controller;
- external-system lifecycle controller;
- projection/sink controller;
- cross-cluster or uncached-dependency controller.

These are reading entry points, not mutually exclusive kinds. Select by behavior,
not a Kind name such as Set or Group. Record the reconciliation unit (object key,
shared destination key, or full set), identity constraints, direct or delegated
side effects, access domain, and time model. Cross-cluster access and scheduling
can qualify another primary responsibility.

Read `references/controller-patterns.md` before choosing. Do not add phases,
finalizers, patch helpers, polling, `APIReader`, or server-side apply merely
because another controller uses them.

All patterns share these invariants:

- Reconciliation is **level-based**. A request contains a key, not the event
  that caused it; always re-read current state and derive the next action.
- Every write is idempotent. A retry after any successful write must be safe.
- Cache reads are the default; uncached reads are explicit correctness choices.
- Status reports observation and progress. API defaulting owns defaults; spec
  changes are allowed only when the API contract explicitly defines
  controller-owned late initialization or normalization.
- Finalizers protect a concrete obligation before an object may disappear,
  including cleanup or durable completion accounting. Persist the protection
  before the operation that needs it; remove it only when the documented
  obligation is satisfied.
- `status.observedGeneration` follows the API's observation/processing contract.
  It does not imply readiness or convergence; neither nil error nor partial
  progress alone determines whether it advances.

## Before implementation

Inspect the target repository and record:

1. the served API type, validation/defaulting, status/condition contract, and
   status subresource;
2. controller-runtime and Kubernetes dependency versions;
3. controller-manager style: direct setup, descriptor registry, exported
   wrapper layer, or native `manager.Runnable`;
4. existing helpers for patching, conditions, predicates, SSA, events,
   rate-limiting, and result aggregation;
5. cache exclusions and field indexes already installed;
6. the existing component-config block, if the controller consumes one.

Preserve the repository's actual conventions. Do not copy a helper call until
its local implementation and ownership semantics have been read.

Read `references/repository-conventions.md` during this inspection.

## Workflow

### Phase 1 — State the reconcile contract

Write a short facts ledger covering:

- primary resource and scope, reconciliation unit, and shared-write conflict domain;
- desired state and authoritative observed state;
- owned, adopted, referenced, external, and cross-cluster resources;
- event sources and key-mapping rules;
- deletion/accounting obligations and their completion guarantee (confirmed
  absence, accepted deletion, or explicit preservation);
- conditions, phase, references, and observed-generation semantics;
- expected waiting states, transient failures, terminal failures, and recovery
  when an external mutation may have succeeded but its result is unknown.

If these facts are already in types, tests, or the request, do not ask again.
Ask one question only when a missing fact changes the controller's safety or
ownership model.

Read `references/reconcile-contract.md` for the decision table.

### Phase 2 — Select the controller pattern

Choose a primary responsibility from `references/controller-patterns.md` and
record applicable access/time qualifiers. For aggregate controllers, distinguish
count maintenance, rollout, stateful identity, and batch completion. Compose
additional behavior only when it actually exists—for example,
an owned-resource controller that also polls an external API.

State why the chosen pattern needs each of: finalizer, periodic requeue,
secondary watch, uncached reader, SSA, or multi-phase reconcile. Omit any item
without a concrete need.

### Phase 3 — Design watches, indexes, and dependencies

For keyed builder controllers, define `For`, `Owns`, and `Watches` from the contract:

- `For` identifies the one primary resource;
- `Owns` maps controller-owned children through owner references;
- `Watches` handles referenced, adopted, external-event, or cross-cluster
  resources through an explicit map function;
- indexes replace full-list scans for reverse lookups.

Use per-input predicates when primary and secondary resources have different
metadata. A global `WithEventFilter` applies to every watched source and can
silently block child events.

For a full-set or shared-destination loop, define snapshot completeness,
serialization, ownership filtering, and triggers instead of forcing one `For`
per source object. Preserve native Runnable wiring when that fits the contract.

Read `references/repository-conventions.md` for setup and registration examples.

### Phase 4 — Implement convergence

For keyed loops, implement fetch → gates → finalizer persistence (if needed) →
deletion or normal convergence → status persistence. For full-set loops, use the
snapshot → plan → owned apply → next-trigger contract. Business logic should compute from
current state and use stable identities or persisted references.

Use the repository patch helper only after checking its behavior for metadata,
spec, status, condition conflicts, and deletion. If it supports owned
conditions, declare exactly the condition types this controller owns.

Read `references/reconcile-contract.md` before writing the loop.

### Phase 5 — Status, conditions, and errors

Classify every non-success outcome:

- transient failure → return an error for rate-limited retry;
- expected waiting/drift polling → set a progress condition and use a watch or
  `RequeueAfter`, without error backoff;
- optimistic conflict → follow the repository convention, normally a clean
  immediate retry or the returned conflict error;
- terminal/user state → persist a condition/event and stop hot-looping;
- not found primary → normally successful completion; a projection/sink
  controller may first reconcile absence by key.

Derive summary conditions and phase from detailed observations. Persist failure
conditions even when the business operation returns an error. Advance observed
generation according to the API contract, independently of Ready or action completion. An unknown external mutation outcome needs an
identity-recovery or stop condition before another create is attempted.

### Phase 6 — Register and test

Register through the manager's existing mechanism, preserving canonical names,
aliases, feature gates, shared `controller.Options`, scheme registration,
indexes, and injected collaborators. Add or extend component config only by
using `k8s-controller-config`.

Read `references/file-map.md` and `references/testing.md`. Implement the
behavioral matrix appropriate to the selected pattern, run focused tests, then
the repository-wide relevant test target.

## Hard rules

- Never infer correctness from an event payload; requests may be deduplicated,
  delayed, or caused by an unrelated watched object.
- Never mutate spec to emulate API defaulting. A spec write requires an explicit
  API contract for controller-owned late initialization/normalization and a
  conflict-safe update path; otherwise users own spec.
- Never create an externally visible resource before the finalizer or other
  leak-prevention marker protecting it is durably persisted.
- Never treat an accepted asynchronous delete as confirmed absence. Retain the
  finalizer until its promised cleanup/accounting guarantee is satisfied; an
  accepted-delete or orphan policy must be explicit in the API contract.
- Never infer readiness from observed generation or `err == nil`. Preserve the
  API's version-observation semantics during waiting and partial progress.
- Never let two controllers overwrite each other's conditions. Declare and
  patch owned condition types.
- Never combine `Owns` and an equivalent `Watches` for the same relationship
  unless the second mapping intentionally covers a distinct ownership case.
- Never use `APIReader` as a blanket workaround for cache behavior. Document
  the freshness requirement or cache exclusion that needs it.
- Never use `GenerateName` for retryable creation unless the created identity is
  recoverable deterministically or persisted before another create can occur.
- Never assume a fake client proves cache, watch, status-subresource, SSA, or
  optimistic-conflict behavior; use envtest or a targeted integration test.
- Do not recreate component config, generated clients, API types, or apiserver
  storage in this skill.

## Progressive loading

Read only the reference needed for the current phase:

| Phase | Read |
|---|---|
| repository inspection | `references/repository-conventions.md` |
| reconcile contract | `references/reconcile-contract.md` |
| pattern selection | `references/controller-patterns.md` |
| watches/setup/registration | `references/repository-conventions.md` |
| implementation/status/finalizers | `references/reconcile-contract.md` |
| fixed-version source examples | `references/upstream-examples.md` |
| files and tests | `references/file-map.md`, `references/testing.md` |

Do not load every reference up front.

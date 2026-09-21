---
name: k8s-controller
description: >-
  Write a controller that reconciles an already-served API resource: define the
  controller's own component config (internal/controller/<group>/apis/config/),
  then implement the controller-runtime reconciler (Reconciler struct,
  SetupWithManager, Reconcile loop, status/conditions/phase updates, and
  registration) so spec changes converge to observed status. Trigger when the
  user asks to "write a controller", "reconcile <Kind>", "add the controller
  logic", or wire a reconciler into the controller-manager. Covers component
  config, the reconcile loop, status/conditions, and registration. Do not use for
  defining the API types (k8s-crd-api), for apiserver REST storage / client
  codegen (k8s-apiserver-rest), or for e2e tests (k8s-e2e).
---

# Kubernetes Controller Authoring

Implement the reconciliation logic that turns desired spec into observed status
for an already-served resource. A controller is the component that watches a
resource, compares what should exist against what does, and converges the two by
creating/updating owned resources and writing status.

Two cooperating halves, both under `internal/controller/`:

1. **Component config** — the controller-manager binary's own configuration
   (`internal/controller/<group>/apis/config/`), following the versioned
   internal/external + defaulting + validation convention. It is a config-file
   schema, **not** a served resource.
2. **Reconciler** — the controller-runtime `Reconciler` (struct +
   `SetupWithManager` + `Reconcile`) that reacts to events and drives
   status/conditions to convergence.

The reconciler runs on controller-runtime, which wraps the underlying native
machinery (shared informers, a rate-limited workqueue, and a reconcile loop).
The native mechanics — informer → enqueue → rate-limited queue → reconcile —
are the invariants the reconciler expresses; the skill states them explicitly
so the reconciler is written against the model, not the framework's accidents.

Keep all output within `internal/controller/**` plus the controller-manager
registration edit. Do not modify `pkg/apis/**`, the apiserver registry, or tests
under `test/e2e/`.

## When to use

- "Write a controller for `<Kind>`" / "reconcile `<Kind>`".
- "Add the controller logic" after the resource is served and the client is
  generated (both from `k8s-apiserver-rest`).
- "Wire a reconciler into the controller-manager" / "register a controller".

## Model

The reconcile contract, stated once:

- **Read cached, write through clients.** Reads go through the manager's cached
  client (or listers); writes go through typed clients, never by mutating the
  informer cache object in place (`DeepCopy()` first).
- **Not-found is done.** Deletion is observed as absence; `IsNotFound` / the
  equivalent is a no-op, not an error to retry.
- **Retry only transient errors, with backoff.** Returning an error requeues the
  object through a rate limiter; permanent/user errors are recorded (events +
  conditions) and return `nil`.
- **One keyed queue.** Every event (add/update/delete, primary or owned) funnels
  into a single queue keyed by the reconciled object's namespace/name.
- **Converge in status.** All observable progress is persisted through a
  conflict-safe status/conditions path, never into spec.

controller-runtime maps these to `Reconcile(ctx, req)` returning
`(ctrl.Result, error)`, with `For`/`Owns`/`Watches` declaring which events
enqueue the primary object.

## Interview rules (grill style)

1. Ask **one question at a time**; state each question's purpose and offer a
   default so the user can accept with a single keystroke.
2. Keep a **facts ledger**; check the ledger and repo (`internal/controller/**`,
   `pkg/apis/<group>/**`) before asking.
3. **Fast path.** If the user states what the controller watches, what it
   creates/validates, and the terminal condition/phase, do not re-ask — write,
   then confirm once.
4. **Phase order is fixed.** Advance only after the user confirms the phase
   summary.
5. Match the user's language for prose; keep code identifiers in English.

## Classify the request

- **New controller** — no `internal/controller/<group>/` tree yet: write the
  component config AND the reconciler, and register it.
- **New reconciler / new logic** — the group config already exists; add or
  extend one reconciler's `Reconcile` phases and its registration.

Ask a single disambiguating question only when it is genuinely ambiguous.

## Workflow

### Phase 1 — Reconcile contract

Collect, one at a time, skipping what is known:

1. the reconciled `<Kind>` + group (already served)
2. what the controller does on each reconcile (validate spec, check a
   referenced secret, create/update owned resources, mark status)
3. owned resources it creates/manages (for `Owns`) and any secondary watches
4. event filter: paused-annotation gate and/or a watch-filter label value
5. whether it uses a finalizer (deletion needs cleanup) — default no for a
   read-only reconciler
6. the terminal condition/phase and the failure conditions to surface

### Phase 2 — Component config

Only for a new controller group. Define the group config's fields (nested
per-controller blocks, feature gates, and the shared generic block), defaults,
and validation. Reuse the shared generic config; add only domain-specific
fields.

Read `references/config-skeleton.md` in this phase.

### Phase 3 — Reconciler struct + setup

Write the `Reconciler` struct (client, optional uncached `APIReader`,
`ComponentConfig`, `WatchFilterValue`, collaborators) and `SetupWithManager`
(`For` / `Owns` / `Watches` + `WithOptions` + `Named`).

Read `references/reconciler-skeleton.md` in this phase.

### Phase 4 — Reconcile logic

Write the `Reconcile` skeleton: fetch + not-found no-op → pause gate →
patch-helper snapshot + deferred patch → finalizer guard (if any) → deletion vs
normal path → phase sub-reconcilers → aggregate errors and requeue hint.

Read `references/reconciler-skeleton.md` in this phase.

### Phase 5 — Status & conditions

Write the condition constants the controller owns, the `MarkTrue`/`MarkFalse`/
`MarkUnknown` calls, the `SetSummary` for `Ready`, the phase derivation, and the
`observedGeneration` write.

Read `references/reconciler-skeleton.md` (status section) in this phase.

### Phase 6 — Registration

Add the canonical name constant, register the reconciler in the manager's
setup/descriptor wiring, and source worker count + sync period from config.

Read `references/reconciler-skeleton.md` (registration section) and
`references/file-map.md` in this phase.

## Rules

- Write only hand-written files. Never hand-write generated client/lister/
  informer code; import from `pkg/generated/**` (produced by
  `k8s-apiserver-rest`).
- Every exported identifier gets an identifier-first doc comment; every named
  struct field a semantic comment.
- Follow the repository's existing controller naming: package name = controller
  short name, a package-level `controllerName` constant in
  `"controller-manager.<name>"` form, and a `names/` package holding canonical
  name constants.
- Reuse the repository's `internal/pkg/util/{conditions,patch,predicates,
  annotations}` helpers rather than reimplementing condition merge or diff
  patching.
- Never mutate a cached object in place; `DeepCopy()` before writes.
- Run `gofmt` on everything you write.
- Do not expand the task beyond controller config + logic + registration; report
  any apiserver or e2e work as a follow-up.

## Progressive loading

1. Only the `description` above is always present; it is the trigger.
2. When triggered, this SKILL.md loads; it carries the workflow.
3. Read a reference only when the current phase needs it, then stop.

| Phase | Read (on demand) |
|---|---|
| 1 — Reconcile contract | nothing |
| 2 — Component config | `references/config-skeleton.md` |
| 3 — Reconciler struct + setup | `references/reconciler-skeleton.md` |
| 4 — Reconcile logic | `references/reconciler-skeleton.md` |
| 5 — Status & conditions | `references/reconciler-skeleton.md` (status section) |
| 6 — Registration | `references/reconciler-skeleton.md` (registration section), `references/file-map.md` |

Do not pre-load all references.
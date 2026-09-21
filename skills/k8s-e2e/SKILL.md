---
name: k8s-e2e
description: >-
  Write end-to-end tests that exercise a Kubernetes control plane's full
  reconcile link against a running cluster: create a resource through the
  generated clientset, let the apiserver persist it and the controller reconcile
  it, and assert the observed status (phase, conditions, observedGeneration)
  converges. Trigger when the user asks for an e2e test, a smoke test of the
  CRD→controller→status path, or an end-to-end verification of a resource.
  Covers the ginkgo-based test suite layout, kubeconfig client setup, and
  eventually-consistent status assertions. Do not use for unit tests, fake-client
  tests, apiserver/storage wiring, or controller logic itself.
---

# Kubernetes End-to-End Tests

Verify the whole control-plane link — resource creation through the served API,
persistence, controller reconciliation, and status convergence — against a
running control plane (a local cluster, usually provisioned with `kind`),
driven by the generated clientset.

Keep the e2e suite under `test/e2e/`. It talks to a cluster through a
kubeconfig; it does not spin up the apiserver or controller in-process, and it
does not assert controller internals — only observable spec/status transitions.

## When to use

- "Add an e2e test for `<Kind>`" / "smoke-test the reconcile loop".
- "Verify the CRD → controller → status path end to end".
- The resource is already served (k8s-apiserver-rest) and reconciled
  (k8s-controller); e2e comes last and depends on both.

## Model

An e2e suite has two parts:

1. **Suite bootstrap** — `test/e2e/e2e_test.go`: a `TestMain` (or ginkgo
   `Suite`) that parses the test flags, loads the cluster kubeconfig, builds the
   clientset, and registers cleanup.
2. **Feature specs** — `test/e2e/<feature>_test.go`: ginkgo specs, each with a
   `BeforeEach` that namespaces its objects, a body that creates a resource,
   waits for the controller to converge, and asserts the observed state with
   gomega `Eventually`/`Consistently`.

The test asserts **eventually-consistent** status: a controller reconciles
asynchronously, so assertions poll against the live cluster rather than checking
the create response.

## Interview rules (grill style)

1. Ask **one question at a time**; state each question's purpose and offer a
   default so the user can accept with a single keystroke.
2. Keep a **facts ledger**; check the ledger and repo (`test/e2e/**`,
   `pkg/generated/**`) before asking.
3. **Fast path.** If the user names the resource and the expected terminal
   status, do not re-ask — write the spec, then confirm.
4. **Phase order is fixed.** Advance only after the user confirms the phase
   summary.
5. Match the user's language for prose; keep code identifiers in English.

## Workflow

### Phase 1 — Target & expected outcome

Collect, one at a time, skipping what is known:

1. resource + namespace behavior (namespaced vs cluster-scoped)
2. the create input (a minimal valid spec)
3. the expected terminal state (phase, a condition type, or
   `observedGeneration >= n`) and the timeout budget for convergence

### Phase 2 — Suite layout

Confirm the suite bootstrap already exists under `test/e2e/`; if not, write it.
Confirm the cluster provisioner (`kind`) and the `kubeconfig` source.

Read `references/spec-skeleton.md` in this phase.

### Phase 3 — Specs

For each resource, write one spec (create → converge → assert) and one teardown
path. Keep specs independent and namespace-isolated.

### Phase 4 — Run & document

Run locally against a provisioned cluster and via the repository's e2e target
(`make test-e2e` or equivalent). Remind the user the cluster and built binaries
must be available first.

## Rules

- Write only the hand-written spec files. Never hand-write generated client
  code; import it from `pkg/generated/clientset` and `pkg/generated/...`.
- Assert via gomega `Eventually` with an explicit timeout and polling interval;
  never a one-shot equality check on a freshly created object.
- Give every spec a unique, namespace-isolated fixture so parallel runs do not
  collide.
- Clean up created objects in `AfterEach`/`DeferCleanup`, and tolerate
  already-deleted resources so re-runs are idempotent.
- Use the repository's own kubeconfig/env conventions (flag name, env var) and
  clientset constructor; do not hardcode cluster addresses or a foreign module
  path in the spec.
- Do not expand the task beyond the e2e whitespace; report anything that must
  change in the controller or apiserver as a follow-up, not as an e2e hack.

## Progressive loading

1. Only the `description` above is always present; it is the trigger.
2. When triggered, this SKILL.md loads; it carries the workflow.
3. Read a reference only when the current phase needs it, then stop.

| Phase | Read (on demand) |
|---|---|
| 1 — Target & outcome | nothing |
| 2 — Suite layout | `references/spec-skeleton.md` |
| 3 — Specs | `references/spec-skeleton.md` |
| 4 — Run & document | nothing |

Do not pre-load all references.
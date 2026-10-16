# Reconcile contract

Read this reference before implementing the loop, status, or finalization.

## Level-based contract

A controller-runtime request carries only the primary object's key. The event
may be duplicated, collapsed with other events, delayed, or caused by a
secondary object. Reconcile therefore answers one question:

> Given current desired and observed state, what is the smallest safe action
> that moves this key toward convergence?

Do not branch on a remembered event. Re-fetch the primary and all state needed
for the decision.

API defaulting owns ordinary defaults. Controller writes to spec are exceptional
and require an explicit API contract for controller-owned late initialization
or normalization; otherwise desired spec remains user-owned.

## Outcome model

Distinguish completion from call success. A reconcile can return `nil` while it
is still waiting for a dependency or an asynchronous operation.

| State | Status action | Return |
|---|---|---|
| primary not found | normally none; projection/sink may delete or tombstone by key | zero result after absence handling, nil |
| converged for current generation | Ready/success; observed generation per API contract | zero result, nil, or poll interval for external drift |
| expected dependency not ready | progress/Unknown condition | rely on a proven watch or `RequeueAfter`, nil |
| asynchronous create/delete requested | progress condition | explicit requeue/poll, nil |
| transient API/network failure | failure condition/event when useful | error for rate-limited retry |
| optimistic conflict | no stale overwrite | conflict error or clean immediate retry per repo convention |
| invalid/terminal user state | durable failure condition/event | terminal error or zero result; no hot loop |
| deletion cleanup incomplete | Deleting/progress condition | watch/requeue until absence confirmed |

Define when this API considers a generation observed/processed. Track that
separately from progress and convergence; a fully observed generation can still
be waiting for child readiness or an asynchronous operation. A failed required
read may prevent acknowledgement, while a stable invalid spec may be fully
processed. Do not introduce an observedGeneration field or redefine an existing
one merely to match this example.

## Top-level loop

This is a shape, not a mandatory byte-level template. Omit the finalizer when
the selected controller pattern does not need one. The example uses only
controller-runtime client primitives; substitute a repository helper only when
its contract is understood and equivalent.

```go
func (r *Reconciler) Reconcile(
	ctx context.Context,
	req ctrl.Request,
) (ctrl.Result, error) {
	obj := &apiv1.<Kind>{}
	if err := r.client.Get(ctx, req.NamespacedName, obj); err != nil {
		if apierrors.IsNotFound(err) {
			// Most controllers are done. Projection/sink controllers may instead
			// call an idempotent reconcileAbsent(ctx, req.NamespacedName).
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	ctx = ctrl.LoggerInto(ctx, ctrl.LoggerFrom(ctx).WithValues(
		"namespace", obj.GetNamespace(),
		"name", obj.GetName(),
		"generation", obj.GetGeneration(),
	))

	if r.isPaused(obj) { // only when pause is part of this API's contract
		return ctrl.Result{}, nil
	}

	// Persist a required finalizer before any side effect it protects.
	if obj.GetDeletionTimestamp().IsZero() && needsFinalizer(obj) &&
		!controllerutil.ContainsFinalizer(obj, apiv1.<Kind>Finalizer) {
		before := obj.DeepCopy()
		controllerutil.AddFinalizer(obj, apiv1.<Kind>Finalizer)
		if err := r.client.Patch(
			ctx,
			obj,
			client.MergeFromWithOptions(before, client.MergeFromWithOptimisticLock{}),
		); err != nil {
			if apierrors.IsConflict(err) {
				return ctrl.Result{Requeue: true}, nil
			}
			return ctrl.Result{}, err
		}
		return ctrl.Result{Requeue: true}, nil
	}

	if !obj.GetDeletionTimestamp().IsZero() {
		return r.reconcileDelete(ctx, obj)
	}

	statusBase := obj.DeepCopy()
	result, generationObserved, reconcileErr := r.reconcileNormal(ctx, obj)
	r.summarizeStatus(obj)
	if generationObserved { // API-defined acknowledgement, not convergence
		obj.Status.ObservedGeneration = obj.Generation
	}

	patchErr := r.patchStatus(ctx, statusBase, obj)
	return result, kerrors.NewAggregate([]error{reconcileErr, patchErr})
}

func (r *Reconciler) patchStatus(
	ctx context.Context,
	before, after *apiv1.<Kind>,
) error {
	if apiequality.Semantic.DeepEqual(before.Status, after.Status) {
		return nil
	}
	return r.client.Status().Patch(
		ctx,
		after,
		client.MergeFromWithOptions(before, client.MergeFromWithOptimisticLock{}),
	)
}
```

Patch metadata/spec separately from status. Do not issue an unconditional
full-object `Update` after a cached read. When multiple controllers own
different condition types, the simple status patch above must be replaced by a
conflict-retry merge that preserves unowned conditions; use a repository helper
only when it provides that ownership contract.

`reconcileDelete` owns its status/finalizer persistence because deletion may
need a different patch order and may make the object disappear. A normal-path
`reconcileNormal` returns an API-defined generation acknowledgement separately
from its retry result. For example, a controller may acknowledge the spec while
reporting Progressing as children become ready. A missing input needed to
evaluate that spec may leave acknowledgement false. Neither partial mutation
nor nil error decides this universally.

## Normal convergence

Prefer one clear decision tree. Split into sub-reconcilers only when each owns a
coherent state transition.

### Serial phases

Use serial phases when B depends on A. Stop at the first error or waiting state;
continuing can violate ordering.

```go
type phaseResult struct {
	result   ctrl.Result
	waiting  bool
}

for _, phase := range phases {
	out, err := phase(ctx, obj)
	if err != nil {
		return ctrl.Result{}, false, err
	}
	if out.waiting || !out.result.IsZero() {
		return out.result, false, nil
	}
}
return ctrl.Result{}, true, nil
```

### Independent observers

Independent observers may all run so status reports every failure at once.
Independent mutation sub-reconcilers may also continue when each checks its own
dependencies and owns disjoint effects. State the dependency graph and gates;
independence does not imply concurrency is safe. Aggregate errors/results only
under that contract, rather than copying a continue-all or stop-first loop.

## Idempotent Kubernetes writes

For each desired child:

1. derive a stable key;
2. get/list the current child through an indexed relationship;
3. create only on not-found;
4. on already-exists or retry, verify ownership and continue from current
   state;
5. patch only fields owned by this controller;
6. persist a status reference only after the object identity is known.

Use controller owner references only for resources whose lifecycle is governed
by garbage collection. Validate ownership before adopting an existing object.
Use SSA when the repository already has an ownership-safe SSA helper and the
controller intentionally owns a field set; use merge/strategic patches for
small explicit changes.

`GenerateName` is unsafe in a retryable create path unless retries can discover
the prior create by owner/index or the chosen identity is durably recorded
before another create.

## External side effects

External systems require stricter crash safety:

1. persist the finalizer;
2. resolve references and credentials;
3. observe the external object before every mutation;
4. create only when observation proves absence;
5. use a deterministic external identity when possible;
6. before a non-deterministic create, persist a create-pending marker or
   idempotency token;
7. distinguish known failure from an unknown result: if create may have succeeded,
   recover by stable identity/token or stop automatic creation and expose a
   recovery condition; a pending marker detects ambiguity but is not itself
   provider idempotency;
8. after success, persist identity/details and respect any documented
   read-after-create visibility window before trusting another absent response;
9. poll for asynchronous convergence and complete the finalizer obligation
   according to the declared deletion/accounting policy.

Use a bounded context timeout for provider calls. An external API with no reliable event
source needs polling even while converged so drift is eventually detected.
Use bounded intervals and jitter where many resources could synchronize calls.

## Collection accounting and projection

For anonymous child sets, expectations or equivalent accounting bridges write
success and delayed cache observation. Register intended operations before
writes, consume observations from events, undo expectations for failed or
skipped writes, and clear them when the parent disappears. Define expiry and
restart behavior: in-memory expectations do not prove durable exactly-once or
strict cardinality across failures. Stable identities and indexed discovery
solve different parts of this problem.

For full-set projection, read authoritative current and desired snapshots,
normalize/filter them, calculate a plan, then apply only owned changes allowed
by policy. A failed or incomplete source read must not masquerade as an empty
set and trigger deletion. Specify snapshot completeness, shared destination
conflicts, partial apply recovery, and periodic repair of missed events.

## Finalization

Add a finalizer only for a concrete obligation before the protected object may
disappear. Owner-reference GC can handle lifecycle cleanup, but cannot replace
durable completion accounting. Job-style tracking first persists uncounted
terminal identities, then releases child finalizers, then folds those identities
into counters without losing or double-counting results. Finalizers may protect
a child as well as the primary.

Define the completion guarantee: confirmed absence, accepted deletion with
explicitly weaker guarantees, or preservation/orphaning. Prefer confirmed
absence for new external cleanup contracts; preserve an existing API's declared
policy. Do not silently weaken it to copy an upstream example.

Deletion reconciliation is its own idempotent state machine:

```text
deletion timestamp?
├── no finalizer owned by us → done
├── cleanup not requested → request cleanup, persist progress, requeue
├── cleanup still visible → wait/requeue
├── cleanup failed transiently → condition + error
└── declared obligation satisfied → remove only our finalizer with optimistic patch
```

Never remove other controllers' finalizers. If cleanup depends on resources
owned by another finalizer, document and test the ordering rather than assuming
it.

## Status ownership

Status is a public contract, not a log buffer.

- The controller owns only documented condition types and status fields.
- `LastTransitionTime` changes only when condition status changes.
- `Ready` is derived from detailed conditions when the API defines a summary;
  do not independently toggle it throughout the loop.
- Phase is derived from observed facts/conditions at one well-defined point.
- References identify resources actually observed or created, not planned
  resources.
- Failure messages are concise and safe for users; detailed errors stay in logs.
- Status writes use the status subresource and a conflict-safe patch/retry path.

Set `ObservedGeneration = metadata.generation` at the observation/processing
boundary defined by this API. Keep Ready, Progressing, replica counts, and
external operation completion separate. StatefulSet-like APIs may acknowledge
the generation while work remains; a contract needing an unread dependency may
withhold acknowledgement. Condition-level observedGeneration and an overall
status field can have different owners and boundaries.

## Requeue and error semantics

- Non-nil error: controller-runtime ignores `Result` and uses rate-limited
  exponential backoff, except a supported terminal-error wrapper.
- `RequeueAfter`: expected time-based retry without failure backoff.
- `Requeue: true`: immediate rate-limited retry; use deliberately, commonly for
  an optimistic conflict when local convention prefers a clean retry.
- Zero result: no scheduled retry. It is safe only when a watch, poll, or true
  convergence guarantees future progress.

Avoid returning an error for a dependency that is simply not ready; repeated
errors create noisy backoff and events. Conversely, do not return zero result
for an external state that has no watch and still needs polling.

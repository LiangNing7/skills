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
| converged for current generation | Ready/success; set observed generation | zero result, nil, or poll interval for external drift |
| expected dependency not ready | progress/Unknown condition | rely on a proven watch or `RequeueAfter`, nil |
| asynchronous create/delete requested | progress condition | explicit requeue/poll, nil |
| transient API/network failure | failure condition/event when useful | error for rate-limited retry |
| optimistic conflict | no stale overwrite | conflict error or clean immediate retry per repo convention |
| invalid/terminal user state | durable failure condition/event | terminal error or zero result; no hot loop |
| deletion cleanup incomplete | Deleting/progress condition | watch/requeue until absence confirmed |

Use an explicit `complete`/`fullyObserved` boolean when observed generation is
patched by a defer. Never derive it from `err == nil`.

## Top-level loop

This is a shape, not a mandatory byte-level template. Omit the finalizer and
patch helper when the selected controller pattern does not need them.

```go
func (r *Reconciler) Reconcile(
	ctx context.Context,
	req ctrl.Request,
) (result ctrl.Result, retErr error) {
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

	if annotations.IsPaused(obj) {
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

	helper, err := patch.NewHelper(obj, r.client) // only when this helper exists and fits
	if err != nil {
		return ctrl.Result{}, err
	}

	fullyObserved := false
	defer func() {
		r.summarizeStatus(obj)
		opts := []patch.Option{patch.WithOwnedConditions{
			Conditions: r.ownedConditions(),
		}}
		if fullyObserved {
			opts = append(opts, patch.WithStatusObservedGeneration{})
		}
		if err := helper.Patch(ctx, obj, opts...); err != nil {
			retErr = kerrors.NewAggregate([]error{retErr, err})
		}
	}()

	if !obj.GetDeletionTimestamp().IsZero() {
		return r.reconcileDelete(ctx, obj)
	}

	result, fullyObserved, retErr = r.reconcileNormal(ctx, obj)
	return result, retErr
}
```

If the repository has no suitable patch helper, explicitly snapshot before
mutation and separately patch metadata/spec and status with optimistic locking.
Do not issue an unconditional full-object `Update` after a cached read.

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

Independent read-only observers may all run so status reports every failure at
once. Aggregate their errors only when concurrent/independent execution is
safe. Do not copy an aggregate-errors loop into ordered mutation phases.

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
7. after create/update/delete, persist returned identity/details and poll until
   observation confirms the requested state;
8. remove the finalizer only after confirmed absence/cleanup.

Use a bounded context timeout for provider calls. An external API with no event
source needs a poll `RequeueAfter` even while converged so drift is eventually
detected.

## Finalization

Do not add a finalizer when owner-reference garbage collection fully expresses
cleanup and no external/non-owned resource must be handled.

Deletion reconciliation is its own idempotent state machine:

```text
deletion timestamp?
├── no finalizer owned by us → done
├── cleanup not requested → request cleanup, persist progress, requeue
├── cleanup still visible → wait/requeue
├── cleanup failed transiently → condition + error
└── cleanup confirmed → remove only our finalizer with optimistic patch
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

Set `ObservedGeneration = metadata.generation` only when all inputs needed to
evaluate the generation were successfully observed. It can be correct to set it
while reporting a stable user-facing failure (the generation was fully
evaluated and found invalid), but not while waiting on an unread dependency or
after a partial mutation.

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

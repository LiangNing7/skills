# Reconciler skeleton

The reconciler is a controller-runtime `Reconciler`. controller-runtime wraps the
native machinery — a shared informer cache feeding a rate-limited workqueue that
a reconcile loop drains — so the vocab below maps directly onto it: `For`/`Owns`/
`Watches` declare event handlers that enqueue the primary object's key; `Reconcile`
is the work-queue item handler. `<Kind>` is the reconciled type, `<Resource>` the
resource, `<controller>` the package/short name, `v1beta1` the served version,
`<module>` the module path.

## Reconciler struct + name

```go
package <controller>

import (
	"context"

	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"

	"<module>/internal/controller/<group>/apis/config"
	"<module>/internal/pkg/util/annotations"
	"<module>/internal/pkg/util/conditions"
	"<module>/internal/pkg/util/patch"
	"<module>/pkg/apis/<group>/v1beta1"
)

const controllerName = "controller-manager.<controller>"

// Reconciler reconciles a <Kind> object.
type Reconciler struct {
	client          client.Client
	APIReader       client.Reader // optional: uncached reads for cache-excluded objects
	ComponentConfig *config.<Controller>ControllerConfiguration

	// WatchFilterValue is the label value used to filter events prior to reconciliation.
	WatchFilterValue string

	// ... controller-specific collaborators ...
}

// SetupWithManager sets up the controller with the manager.
func (r *Reconciler) SetupWithManager(ctx context.Context, mgr ctrl.Manager, options controller.Options) error {
	r.client = mgr.GetClient()
	return ctrl.NewControllerManagedBy(mgr).
		For(&v1beta1.<Kind>{}).
		Owns(&v1beta1.<Child>{}).                     // only when it owns resources
		Watches(                                        // only when reacting to a non-owned type
			&v1beta1.<Other>{},
			handler.EnqueueRequestsFromMapFunc(r.otherTo<Kind>)).
		WithOptions(options).
		Named(controllerName).
		Complete(r)
}
```

`controller.Options` carries `MaxConcurrentReconciles`, `RateLimiter`, and
`RecoverPanic` from the manager (worker count = `Generic.Parallelism`; the
limiter is the default `MaxOf` combining exponential per-item backoff with an
aggregate token bucket). The controller does not manage those itself.

## Reconcile loop

The canonical skeleton (finalizer guard + diff-patch + phase sub-reconcilers) is:

```go
func (r *Reconciler) Reconcile(ctx context.Context, req ctrl.Request) (_ ctrl.Result, reterr error) {
	// 1. Fetch; not-found is a no-op (the object was deleted).
	obj := &v1beta1.<Kind>{}
	if err := r.client.Get(ctx, req.NamespacedName, obj); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	// 2. Pause gate: skip objects the user explicitly paused.
	if annotations.IsPaused(obj) {
		return ctrl.Result{}, nil
	}

	// 3. Snapshot for diff patching; always patch on exit.
	helper, err := patch.NewHelper(obj, r.client)
	if err != nil {
		return ctrl.Result{}, err
	}
	defer func() {
		opts := []patch.Option{}
		if reterr == nil {
			opts = append(opts, patch.WithStatusObservedGeneration{})
		}
		if err := helper.Patch(ctx, obj, opts...); err != nil {
			reterr = kerrors.NewAggregate([]error{reterr, err})
		}
	}()

	// 4. Finalizer guard (only when the controller needs deletion cleanup).
	if !controllerutil.ContainsFinalizer(obj, v1beta1.<Kind>Finalizer) {
		controllerutil.AddFinalizer(obj, v1beta1.<Kind>Finalizer)
		return ctrl.Result{}, nil // the finalizer write is itself a patch; reconcile again next event
	}

	// 5. Deletion path.
	if !obj.GetDeletionTimestamp().IsZero() {
		return r.reconcileDelete(ctx, obj) // on success: controllerutil.RemoveFinalizer(obj, ...)
	}

	// 6. Normal path.
	return r.reconcile(ctx, obj)
}
```

Requeue semantics: `(ctrl.Result{RequeueAfter: d}, nil)` reschedules later without
backoff; `(ctrl.Result{}, err)` requeues through the rate limiter;
`(ctrl.Result{}, nil)` is "done". Skip the finalizer guard (§4/§5) when the
reconciler has no deletion work; then `Reconcile` is just fetch → pause →
deferred patch → `reconcile`.

## Phase sub-reconcilers

Break a reconcile into idempotent phases and aggregate the requeue hint:

```go
func (r *Reconciler) reconcile(ctx context.Context, obj *v1beta1.<Kind>) (ctrl.Result, error) {
	phases := []func(context.Context, *v1beta1.<Kind>) (ctrl.Result, error){
		r.reconcileA,
		r.reconcileB,
	}
	res := ctrl.Result{}
	var errs []error
	for _, phase := range phases {
		phaseRes, err := phase(ctx, obj)
		if err != nil {
			errs = append(errs, err)
			break
		}
		res = coreutil.LowestNonZeroResult(res, phaseRes)
	}
	return res, kerrors.NewAggregate(errs)
}
```

Each phase follows an idempotent "already there?" check before creating/updating
an owned object with a controller `OwnerReference`, emitting an event on both
success and failure. Reads go through `r.client`; writes go through
`r.client`/typed clients with a `DeepCopy()` of any cached object first.

## Status & conditions

The controller owns its condition constants (in
`<controller>_status_condition_utils.go`) and mutates them via the conditions
helpers; `Ready` is a **summary** merged by priority, never set by hand:

```go
// on success:
conditions.MarkTrue(obj, v1beta1.<Something>ReadyCondition)

// on a blocking dependency failure:
conditions.MarkFalse(obj, v1beta1.<Something>ReadyCondition,
	v1beta1.<Something>FailedReason, v1beta1.ConditionSeverityError,
	"failed: %v", err)

// roll the other conditions into Ready (priority: False/Error > False/Warning > ... > True):
conditions.SetSummary(obj,
	conditions.WithConditions(
		v1beta1.<A>ReadyCondition,
		v1beta1.<B>ReadyCondition,
	))
```

Phase is derived at the end of reconcile from conditions/refs — not maintained
inline — and `observedGeneration` is written by the deferred patch
(`WithStatusObservedGeneration{}`), so both reflect the last-acted-on spec:

```go
func (r *Reconciler) reconcilePhase(_ context.Context, obj *v1beta1.<Kind>) {
	original := obj.Status.Phase
	if obj.Status.Phase == "" {
		obj.Status.SetTypedPhase(v1beta1.<Kind>PhasePending)
	}
	if obj.Status.Ref != nil && !conditions.IsTrue(obj, v1beta1.<Healthy>Condition) {
		obj.Status.SetTypedPhase(v1beta1.<Kind>PhaseProvisioning)
	}
	if obj.Status.Ref != nil && conditions.IsTrue(obj, v1beta1.<Healthy>Condition) {
		obj.Status.SetTypedPhase(v1beta1.<Kind>PhaseRunning)
	}
	if obj.Status.FailureReason != nil || obj.Status.FailureMessage != nil {
		obj.Status.SetTypedPhase(v1beta1.<Kind>PhaseFailed)
	}
	if !obj.DeletionTimestamp.IsZero() {
		obj.Status.SetTypedPhase(v1beta1.<Kind>PhaseDeleting)
	}
	// record a transition timestamp only when the phase changed
}
```

The root object carries the required accessor pair so the helpers can operate on
it:

```go
// GetConditions returns the conditions for this object.
func (r *<Kind>) GetConditions() v1beta1.Conditions { return r.Status.Conditions }

// SetConditions sets the conditions for this object.
func (r *<Kind>) SetConditions(conditions v1beta1.Conditions) { r.Status.Conditions = conditions }
```

If writing status through a plain typed client instead of the patch helper, wrap
the `UpdateStatus` in a conflict-retry loop that re-gets on `IsConflict` and
fails hard if the UID changes underneath.

## Registration

1. Add the canonical name constant to the `names/` package (a plain const,
   treated as an ID; only ever aliased, never renamed).
2. In the manager entry, register the reconciler with its config block and shared
   options — either through the descriptor map / `setupReconcilers`, e.g.:

```go
if err := (&<controller>ctrl.Reconciler{
	ComponentConfig:  &cctx.Config.ComponentConfig.<Controller>Controller,
	WatchFilterValue: cctx.Config.ComponentConfig.Generic.WatchFilterValue,
}).SetupWithManager(ctx, mgr, cctx.ControllerOptions); err != nil {
	return err
}
```

The shared `controller.Options` (worker count from `Generic.Parallelism`, default
rate limiter, panic recovery) is built once from config and handed to every
reconciler; individual controllers may override worker count from their own
config block.
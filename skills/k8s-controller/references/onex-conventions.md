# Onex-derived controller conventions

Read this reference while inspecting the repository and wiring watches or
registration. Onex-derived repositories do not all use the same manager shape;
the code in the target repository is authoritative.

## First classify the manager

Look for one of these registration styles before adding files:

1. **Dedicated manager** — a binary has `setupReconcilers` and constructs every
   reconciler directly. Inject dependencies and the existing component-config
   block in that function.
2. **Shared controller-manager** — canonical names feed a
   `ControllerDescriptor`/`AddFunc` registry with enablement, aliases, feature
   gates, and shared options. Add a descriptor; do not bypass the registry.
3. **Wrapper/alias layer** — exported wrappers under `internal/controller`
   expose otherwise internal reconcilers to a batteries-included manager.
   Preserve that boundary when the target uses it.
4. **Runnable/native controller** — special controllers may be added with
   `mgr.Add` instead of controller-runtime builder wiring. Use only when the
   controller does not fit keyed reconciliation.

Canonical controller names are stable IDs used by flags, metrics, logs, and
service accounts. Follow the repository's naming and alias policy; never rename
an existing ID casually.

## Package shape

Prefer a small package organized by responsibility, not by an obligatory file
count:

```text
internal/controller/<domain>/<controller>/
├── controller.go        # Reconciler, setup, top-level dispatch
├── reconcile.go         # normal convergence when it is substantial
├── delete.go            # finalization when it is substantial
├── mapping.go           # secondary-watch map functions and index keys
├── status.go            # owned condition/phase derivation
└── controller_test.go   # behavioral tests
```

Keep a simple observer in one file. Split only when responsibilities are real.
Do not create a second component-config tree; consume the block produced by
`k8s-controller-config`.

## Reconciler dependencies

Use the narrowest dependency surface that is testable:

```go
type Reconciler struct {
	client client.Client

	// Set only when a documented freshness or cache-exclusion requirement exists.
	APIReader client.Reader

	ComponentConfig *config.<Controller>ControllerConfiguration
	WatchFilterValue string
	recorder         record.EventRecorder
	clock            clock.Clock

	// External systems and complex collaborators should be interfaces.
	external ExternalClient
}
```

- Initialize manager-owned dependencies in `SetupWithManager`.
- Inject external clients, clocks, and policy collaborators before setup.
- Use `mgr.GetClient()` for ordinary reads and all Kubernetes writes.
- If the repository exposes raw informer/lister objects or disables cache deep
  copies, `DeepCopy` before mutation. Never mutate shared cache state in place.
- Use `mgr.GetAPIReader()` only for cache-excluded objects or a specific
  read-after-write/freshness invariant. Explain it in a comment and test it.
- Inject a clock for schedules, deadlines, grace periods, and polling tests.

## SetupWithManager

Build watches from the reconcile contract. Apply predicates to the input they
describe instead of globally when primary and secondary resources differ.

```go
func (r *Reconciler) SetupWithManager(
	ctx context.Context,
	mgr ctrl.Manager,
	options controller.Options,
) error {
	r.client = mgr.GetClient()
	r.recorder = mgr.GetEventRecorderFor(controllerName)

	primaryPredicates := []predicate.Predicate{
		predicates.ResourceNotPaused(ctrl.LoggerFrom(ctx)),
		predicates.ResourceHasFilterLabel(ctrl.LoggerFrom(ctx), r.WatchFilterValue),
	}

	return ctrl.NewControllerManagedBy(mgr).
		Named(controllerName).
		For(&apiv1.<Kind>{}, builder.WithPredicates(primaryPredicates...)).
		Owns(&childv1.<Child>{}, builder.WithPredicates(childPredicates...)).
		Watches(
			&corev1.Secret{},
			handler.EnqueueRequestsFromMapFunc(r.secretTo<Kind>),
			builder.WithPredicates(secretPredicates...),
		).
		WithOptions(options).
		Complete(r)
}
```

Adapt the builder API to the controller-runtime version in `go.mod`.

### Watch rules

- `For` is called once for the primary resource.
- `Owns` is for children with a controller owner reference to the primary.
- `Watches` is for references, adoption, cross-cluster sources, external event
  channels, or ownership mappings that `Owns` cannot express.
- Do not `Owns(child)` and also watch the same child with the same owner mapping;
  it creates duplicate enqueue paths without adding correctness.
- A map function returns zero or more primary keys and performs no writes.
- Filter secondary events on fields the secondary resource actually carries.
  A global primary label/pause predicate can accidentally discard every child
  event.
- A generation-changed predicate must still allow deletion timestamp,
  finalizer, pause, and controller-owned annotation transitions required for
  progress. Do not apply it globally without composing those exceptions.

## Indexes and reverse lookups

Install a field index when a watched referenced object must map back to primary
resources. Index registration belongs before manager start and uses the exact
field read by the map/list path.

```go
const secretNameIndex = "spec.provider.apiKeySecret.name"

if err := mgr.GetFieldIndexer().IndexField(
	ctx,
	&apiv1.<Kind>{},
	secretNameIndex,
	func(obj client.Object) []string {
		workload := obj.(*apiv1.<Kind>)
		if workload.Spec.Provider.APIKeySecret.Name == "" {
			return nil
		}
		return []string{workload.Spec.Provider.APIKeySecret.Name}
	},
); err != nil {
	return err
}
```

The lookup must also constrain namespace for namespaced references. Avoid a
cluster-wide `List` on every Secret event.

## Manager-provided options

The manager normally owns:

- concurrency;
- panic recovery;
- rate limiter and queue;
- leader-election participation;
- cache sync timeout.

Use the shared `controller.Options` constructed by the manager. Override one
field only when a controller-specific component-config knob or workload model
requires it. A custom rate limiter needs a concrete throughput/backoff reason
and tests; controller-runtime already defaults to per-key exponential backoff
plus aggregate rate limiting.

## Registration checklist

- scheme contains the primary and every watched/written type;
- required field indexes are installed before controllers start;
- event recorder component uses the canonical controller name;
- canonical name/aliases and descriptor entry are present when that registry is
  used;
- component config reaches the reconciler without being dropped;
- feature-gate and disabled-by-default behavior follows neighboring entries;
- required clients/clusters are added to the manager before setup;
- RBAC markers/manifests cover get/list/watch plus actual write and status verbs.

## Repository helpers

Onex repositories often carry `conditions`, `patch`, `predicates`, `ssa`, and
result-combination helpers derived from Cluster API. Read their implementation
before use:

- Does the patch helper patch metadata/spec and status separately?
- Does it retry condition conflicts and support owned conditions?
- What happens while deletion is in progress?
- Does its observed-generation option mutate status automatically?
- Does an SSA helper preserve fields owned by other managers?
- Does a predicate apply to all builder inputs or one input only?

Use the helper when its contract matches. Otherwise prefer a small explicit
patch over cargo-culting a complex wrapper.

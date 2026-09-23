# Controller file map

The selected pattern determines the files. Keep simple controllers compact;
split complex state machines by responsibility.

## Always inspect or edit

```text
internal/controller/<domain>/<controller>/controller.go
internal/controller/<domain>/<controller>/controller_test.go
<controller-manager canonical names file>
<controller-manager registration or setup file>
```

The controller-manager edits may be a direct `setupReconcilers` call, a
`ControllerDescriptor`/`AddFunc`, or a wrapper alias. Follow the repository.

## Conditional controller files

```text
internal/controller/<domain>/<controller>/doc.go       # when neighboring packages use package docs
internal/controller/<domain>/<controller>/mapping.go   # secondary-watch map funcs and index keys
internal/controller/<domain>/<controller>/status.go    # substantial condition/phase derivation
internal/controller/<domain>/<controller>/delete.go    # substantial finalization state machine
internal/controller/<domain>/<controller>/reconcile.go # substantial normal convergence
internal/controller/<domain>/<controller>/plan.go      # aggregate/scaler desired-vs-current plan
internal/controller/<domain>/<controller>/external.go  # external provider adapter/lifecycle helpers
```

Do not create every conditional file by default.

## Pattern additions

### Observer/status

- referenced-object field index registration;
- secondary map-function tests;
- status/condition tests.

No finalizer or deletion file unless the observer owns real cleanup.

### Owned-resource

- child desired-object builder or reconcile helper;
- child ownership/drift tests;
- `Owns` registration and RBAC writes.

### Aggregate/scaler

- plan/diff file and table tests;
- indexes/expectations bookkeeping;
- adoption/release and deterministic scale-selection tests.

### Scheduled

- schedule calculation helper and injected clock;
- schedule boundary/concurrency/history tests.

### External lifecycle

- provider interface/adapter;
- finalization and create-leak-safety tests;
- periodic poll and timeout configuration consumption.

### Projection/sink

- sink interface and stable projection key;
- upsert/delete or tombstone/sweeper implementation;
- retry, deduplication, and deletion-guarantee tests.

### Cross-cluster

- remote cluster/client dependency wiring;
- remote source watch and map function;
- freshness/reconnect tests.

## Existing component config

Consume an existing per-controller config block in the reconciler and
registration. If a genuinely new knob is required, invoke
`k8s-controller-config` to extend:

```text
internal/controller/<domain>/apis/config/types.go
internal/controller/<domain>/apis/config/v1beta1/types.go
internal/controller/<domain>/apis/config/v1beta1/defaults.go
internal/controller/<domain>/apis/config/validation/validation.go
```

Do not recreate or redesign the config tree from this skill.

## Never hand-write here

- `pkg/generated/clientset`, listers, informers, or apply configurations;
- `zz_generated.*` config/API files;
- served API types and validation;
- apiserver REST storage;
- e2e suites outside the controller's focused test package.

Report missing prerequisites and route them to the appropriate skill.

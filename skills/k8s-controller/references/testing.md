# Controller verification

Controller tests prove convergence and retry safety, not just branch coverage.

## Test layers

### Pure/unit tests

Extract deterministic functions where useful:

- desired child builders;
- aggregate diff/scale plans;
- phase/condition derivation;
- map functions and index extraction;
- schedule calculations;
- deletion-policy decisions;
- external observe/create/update/delete decision logic.

Use table tests with semantic inputs and outputs. Inject clocks, external
clients, and policy interfaces.

### Client-backed unit tests

A controller-runtime fake client is useful for basic get/list/create/patch
flows, but it does not prove real cache propagation, field indexes, watch
delivery, resource-version conflicts, SSA ownership, admission/defaulting, or
status-subresource semantics. State those limits in the test design.

Use an intercepting/counting client when the invariant is “second reconcile
performs no write” or “only status was patched.”

### Envtest/integration tests

Use envtest or the repository's API-server test environment for behavior that
depends on API machinery:

- status subresource isolation;
- optimistic-lock conflicts and retries;
- field indexes used by map/list paths;
- owner references and garbage collection assumptions (where the environment
  supports them);
- SSA field ownership;
- manager cache and watch-triggered reconciliation;
- finalizer persistence/removal.

Use a real cluster e2e only for the full served-API → controller → status path;
that belongs to `k8s-e2e`.

## Minimum behavioral matrix

Select applicable cases; do not create irrelevant boilerplate.

| Behavior | Required assertion |
|---|---|
| primary not found | success/no write, or the selected projection absence action |
| paused/filter mismatch | no business side effect; resume event remains possible |
| already converged | no semantic write and no hot-loop |
| first finalizer reconcile | finalizer persisted before side effect; explicit retry |
| desired child absent | exactly one safe create; owner/key correct |
| retry after successful create | no duplicate create |
| child drift | patch only owned fields |
| dependency waiting | progress condition plus watch or bounded requeue |
| transient failure | failure condition/event plus retryable error |
| terminal user state | durable condition, no rate-limited hot loop |
| deletion requested | cleanup requested once/idempotently |
| deletion still pending | finalizer retained |
| deletion confirmed | only owned finalizer removed |
| status conflict | re-get/merge or safe retry; other conditions preserved |
| partial progress | observed generation not advanced |
| fully evaluated generation | observed generation equals metadata generation |
| secondary event | map function enqueues the correct primary key(s) |
| second identical reconcile | no additional side effect/write |

## Pattern-specific cases

### Aggregate/scaler

- cache lag after create/delete does not exceed desired cardinality;
- adoption rejects mismatched UID/controller ownership;
- scale-up/down selection is deterministic;
- partial mutation resumes from observed state;
- large sets respect per-reconcile bounds.

### Scheduled

- injected time at schedule boundaries;
- missed runs and starting deadline;
- suspend and each concurrency policy;
- duplicate reconcile for one scheduled timestamp creates one child;
- next `RequeueAfter` is positive and correct.

### External lifecycle

- observe-existing avoids create;
- create-pending marker persists before non-deterministic create;
- crash/retry after provider success cannot leak a second resource;
- accepted asynchronous delete retains finalizer;
- not-found confirmation removes finalizer;
- provider timeout/error is retryable and status is preserved;
- Ready state still polls for drift.

### Cross-cluster

- remote watch maps to the local primary;
- unavailable credentials/cluster become a stable condition;
- stale cache does not violate the documented freshness contract;
- reconnect/poll path eventually resumes convergence.

### Projection/sink

- repeated delivery produces one equivalent projection;
- out-of-order/stale input cannot overwrite a newer version when the sink
  exposes versioning;
- primary not-found applies the selected delete/tombstone policy;
- sink failure retries without losing the projection key;
- a sweeper repairs missed deletes when deletion is not finalizer-backed.

## Verification commands

1. `gofmt` every changed Go file.
2. Run focused package tests, preferably with `-race` for code containing
   goroutines, shared caches, or mutable fakes.
3. Run envtest/integration packages when API machinery behavior changed.
4. Run the repository's lint/static checks relevant to controller code.
5. Review the diff for generated files or unrelated rewrites; controller logic
   should not hand-edit generated clients or API code.

## Test quality checks

- Assert status condition type, status, reason, severity, and observed
  generation—not only that “an update happened.”
- Assert action counts for idempotency.
- Avoid `time.Sleep`; use injected clocks or eventual assertions tied to a
  specific watch/reconcile outcome.
- Make every expected requeue explicit.
- Verify failure status is persisted even when reconcile returns an error.
- Ensure test objects use valid metadata/resource versions when exercising
  update/status paths.

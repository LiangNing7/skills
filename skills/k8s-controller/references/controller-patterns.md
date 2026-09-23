# Controller pattern selection

Choose the smallest primary pattern matching the resource. The examples are
decision aids, not templates to combine wholesale.

## Decision table

| Question | Pattern |
|---|---|
| Only observe referenced Kubernetes objects and report status? | Observer/status |
| Create or update a small fixed set of owned children? | Owned-resource |
| Reconcile a variable-size child set or rollout? | Aggregate/scaler |
| Act at computed wall-clock times? | Scheduled |
| Manage a cloud/SaaS/database object with no reliable watch? | External lifecycle |
| Project Kubernetes state into a database, index, or event sink? | Projection/sink |
| Read/write another cluster or cache-excluded object? | Cross-cluster/uncached dependency |

Start with one. Compose only the behaviors that actually exist.

## 1. Observer/status controller

Use for validation/health synthesis from Kubernetes dependencies, such as
checking a referenced Secret and reporting Ready.

Characteristics:

- no finalizer when it owns no cleanup;
- primary `For` plus watches on referenced types;
- reverse-reference field index and map function;
- cached reads are normally sufficient;
- status patch only when semantic status changed;
- no periodic requeue when every changing input has a reliable watch.

This is the default for simple APIs. Do not introduce child phases or an
external lifecycle framework.

## 2. Owned-resource controller

Use when one primary creates/updates a bounded set of Kubernetes children.

Characteristics:

- `Owns` for controller-owned child events;
- stable child names or deterministic discovery by owner/index;
- owner reference and ownership validation;
- create-or-patch/SSA of controller-owned fields;
- finalizer only for cleanup not handled by garbage collection;
- Ready summarizes child existence/readiness.

Reconcile desired objects from scratch each time. Do not treat a child update
event as an instruction; it only triggers re-observation.

## 3. Aggregate/scaler controller

Use for ReplicaSet/MachineSet-style variable child sets, rollout, adoption, or
ordered scale operations.

Additional requirements:

- indexed list by owner/selector;
- explicit adoption/release rules and UID checks;
- deterministic diff: current, desired, create set, update set, delete set;
- bounded mutations per reconcile when fan-out can overload the API;
- expectations or equivalent accounting when cache lag can cause duplicate
  creates/deletes;
- stable ordering for victim selection and rollout decisions;
- status computed from the entire observed set.

This pattern deserves dedicated plan/diff unit tests. A generic serial phase
loop is insufficient.

## 4. Scheduled controller

Use for CronJob-like resources.

Characteristics:

- injected clock;
- calculate missed schedules and the next schedule from persisted/current
  state;
- enforce deadline, suspend, and concurrency policy explicitly;
- `RequeueAfter` until the next schedule;
- watch active children for early completion;
- deterministic child identity for a scheduled time;
- prune history independently from scheduling.

Never rely only on resync periods for correctness. Test time zones, clock skew,
missed intervals, duplicate reconciles at the same scheduled time, and very
small/large `RequeueAfter` values.

## 5. External-system lifecycle controller

Use for cloud resources, remote services, databases, or anything outside the
Kubernetes watch graph.

Characteristics:

- finalizer before create/update side effects;
- observe-first create/update/delete decision;
- deterministic external ID or persisted create-pending/idempotency marker;
- provider-call timeouts and injected interface;
- periodic drift polling while Ready;
- explicit management/deletion policy when orphaning is supported;
- asynchronous delete confirmation before finalizer removal;
- connection details/credentials written through a separately owned path.

Treat “provider accepted request” as progress, not convergence. Persist status
and poll until observation confirms the target state.

## 6. Projection/sink controller

Use when Kubernetes is authoritative and a database, search index, cache, or
event stream is a derived projection.

Characteristics:

- idempotent upsert keyed by namespace/name and, when identity matters, UID;
- primary object fetch followed by projection of the latest complete state;
- an explicit absence/deletion strategy: key-based delete on not-found,
  finalizer-backed guaranteed removal, tombstones, or a periodic sweeper;
- no mutation of primary spec merely to support the sink;
- status writes only when projection health is part of the API contract;
- bounded retry/backoff and deduplication for at-least-once events.

Choose the deletion guarantee deliberately. A controller-runtime request for a
deleted object contains only its key; if the sink needs UID or old content after
deletion, persist that identity, use a finalizer, or consume a durable event
stream. Do not assume the deleted object can still be fetched.

## 7. Cross-cluster or uncached-dependency controller

Use when dependencies live in a provider/workload cluster or are intentionally
excluded from the manager cache.

Characteristics:

- injected `cluster.Cluster`, typed client, or explicit `APIReader`;
- watches wired against the correct cache/source, not the primary manager cache;
- mapping from remote objects to local primary keys;
- separate credentials/readiness handling for the remote cluster;
- no assumption of read-your-write across caches;
- bounded polling fallback if the remote watch can disconnect or omit events.

Document which client reads which object. Tests should make stale/freshness
assumptions visible.

## Combining patterns

Legitimate combinations include:

- owned-resource + external polling when a child drives a provider operation;
- aggregate/scaler + scheduled for batch windows;
- observer + cross-cluster for remote health.
- observer + projection/sink for status plus a derived database view.

Composition does not mean concatenating skeletons. Define one top-level state
machine and state which subsystem owns each condition, write, retry, and
finalizer.

## Evidence behind these patterns

The design deliberately combines several upstream styles:

- controller-runtime's level-based `Reconciler` and queue result semantics;
- Kubernetes Deployment/Job controllers' indexed aggregate state,
  expectations, delayed queues, and rate-limited retries;
- Cluster API's conflict-safe conditions/patch ownership and lifecycle phases;
- Karpenter's optimistic finalizer persistence and explicit async lifecycle;
- Crossplane's observe-first external resource protocol, polling, and
  create-leak prevention.

The target repository's versions and helpers remain authoritative; upstream
examples justify invariants, not byte-for-byte copying.

Primary implementation references:

- controller-runtime
  [`pkg/reconcile`](https://github.com/kubernetes-sigs/controller-runtime/blob/main/pkg/reconcile/reconcile.go)
  for level-based requests and result/error semantics;
- Kubernetes
  [`pkg/controller/deployment`](https://github.com/kubernetes/kubernetes/tree/master/pkg/controller/deployment)
  and [`pkg/controller/job`](https://github.com/kubernetes/kubernetes/tree/master/pkg/controller/job)
  for aggregate state, expectations, delayed work, and rate-limited queues;
- Cluster API
  [`internal/controllers/machine`](https://github.com/kubernetes-sigs/cluster-api/tree/main/internal/controllers/machine)
  for patch/condition ownership and lifecycle decomposition;
- Karpenter
  [`nodeclaim/lifecycle`](https://github.com/kubernetes-sigs/karpenter/tree/main/pkg/controllers/nodeclaim/lifecycle)
  for optimistic finalizer writes and asynchronous lifecycle confirmation;
- Crossplane Runtime
  [`managed/reconciler.go`](https://github.com/crossplane/crossplane-runtime/blob/master/pkg/reconciler/managed/reconciler.go)
  for observe-first external reconciliation, polling, and create-leak safety.

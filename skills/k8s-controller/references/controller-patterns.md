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

These categories are engineering entry points, not an official or exclusive
taxonomy. Choose by responsibility, not a Set/Group suffix. Record these
orthogonal dimensions alongside the primary pattern:

- reconciliation unit and conflict domain: object key, shared output key, full set;
- identity: interchangeable replicas, ordinal/storage identity, external ID;
- effects: direct management or delegated lifecycle orchestration;
- access: local cache, uncached dependency, remote cluster, external API;
- triggers: reliable events, wall-clock scheduling, drift polling.

A small/bounded child set alone does not make a controller simple: rollout,
identity, completion, and shared-write constraints decide the needed machinery.
Start with one primary responsibility and add only applicable qualifiers.

## 1. Observer/status controller

Use for validation/health synthesis from Kubernetes dependencies, such as
checking a referenced Secret and reporting Ready.

Characteristics:

- no finalizer when it owns no pre-deletion obligation;
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
- finalizer only for a pre-deletion obligation not handled by garbage collection;
- Ready summarizes child existence/readiness.

Reconcile desired objects from scratch each time. Do not treat a child update
event as an instruction; it only triggers re-observation.

## 3. Aggregate/scaler controller

Use for ReplicaSet/MachineSet-style variable child sets, rollout, adoption, or
ordered scale operations.

Choose the applicable subtype before designing a generic diff:

| Subtype | Example | Defining invariant |
|---|---|---|
| Count maintenance | ReplicaSet | observe active set and close cardinality gap |
| Rollout | Deployment | version replacement respects availability and surge budgets |
| Stateful identity | StatefulSet | ordinal, storage, revision, and ordered/parallel policy |
| Batch/completion | Job | finite completion/failure with durable result accounting |

Select the mechanisms the subtype actually needs:

- indexed listing by owner/selector and whole-set status;
- adoption/release only when supported, with fresh ownership/UID checks;
- a deterministic plan constrained by availability, identity, or completion policy;
- bounded writes and slow-start where fan-out could overload the API;
- expectations or equivalent accounting across cache lag, with failure rollback,
  observation, expiry, and restart semantics;
- stable victim selection or ordinal ordering when the policy requires it;
- durable terminal identities/counters and child tracking finalizers for
  completion accounting when object disappearance could lose results.

A count controller need not update each child, a rollout controller should not
bypass its child controllers, and a stateful controller cannot treat a
terminating identity as a freely replaceable replica. Use focused plan/policy
tests; a generic serial phase loop is insufficient.

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

- finalizer or equivalent durable protection before the side effects it protects;
- observe-first create/update/delete decision;
- stable external ID or provider idempotency token; if using create-pending
  markers, define unknown-outcome detection and recovery before retrying create;
- a visibility grace period when successful creates may temporarily observe absent;
- provider-call timeouts and injected interface;
- periodic drift polling while Ready;
- explicit management/deletion policy when orphaning is supported;
- asynchronous delete confirmation when the contract promises absence; explicit
  preservation or accepted-delete policy otherwise;
- connection details/credentials written through a separately owned path.

A delegated lifecycle controller instead coordinates provider-owned Kubernetes
objects and their status; do not force a direct provider SDK protocol onto it.

Treat “provider accepted request” as progress, not confirmed convergence. Persist status
and poll until observation confirms the target state.

## 6. Projection/sink controller

Use when Kubernetes is authoritative and a database, search index, cache, or
event stream is a derived projection.

Choose keyed projection or full-set planning. For a shared/full-set output,
read complete source and destination snapshots, normalize and diff them, apply
ownership filters and sync/upsert-only/create-only policy, then execute the
plan. A source error or incomplete snapshot must not become destructive absence.
Define conflicts between sources, partial apply recovery, and periodic repair.
A native loop can fit better than one `For` per source object.

For keyed projection:

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

For fixed-version implementation examples and their transfer limits, read
[upstream-examples.md](upstream-examples.md). These are source-reading aids, not
production templates or claims that upstream code satisfies every rule here.

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

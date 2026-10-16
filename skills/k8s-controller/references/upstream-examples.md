# Fixed-version controller reading examples

Read the row matching the selected responsibility. These releases are pinned
for reproducibility, not recommendations of the latest dependency versions.
Mechanisms must be adapted to the target API contract and repository helpers.
No local knowledge-vault path is required to use this skill.

| Responsibility | Fixed source and useful entry points | Transfer limit |
|---|---|---|
| Status observer | [cert-manager v1.18.2 readiness](https://github.com/cert-manager/cert-manager/blob/686afa62160249022a0205d3a9bf5f059476c684/pkg/controller/certificates/readiness/readiness_controller.go): ProcessItem, updateOrApplyStatus | One Kind can have multiple controllers; SSA and UpdateStatus paths have different ownership mechanics. |
| Fixed children | [sample-controller v0.34.1](https://github.com/kubernetes/sample-controller/blob/05c8ef21b12d19f2a4ceb0bd595488dc32d79b93/controller.go): syncHandler, handleObject | Teaching baseline; unconditional status updates and simplified child updates are not production patch guidance. |
| Count maintenance | [Kubernetes v1.34.1 ReplicaSet](https://github.com/kubernetes/kubernetes/blob/93248f9ae092f571eb870b7664c534bfc7d00f03/pkg/controller/replicaset/replica_set.go): manageReplicas, claimPods, slowStartBatch | Generated names plus expectations coordinate anonymous sets; this does not prove strict cardinality across restart or expiry. |
| Rollout | [Kubernetes v1.34.1 Deployment](https://github.com/kubernetes/kubernetes/blob/93248f9ae092f571eb870b7664c534bfc7d00f03/pkg/controller/deployment/rolling.go): rolloutRolling, reconcileOldReplicaSets | Direct children are ReplicaSets; availability budgets are distinct from child existence and desired count. |
| Stateful identity | [Kubernetes v1.34.1 StatefulSet](https://github.com/kubernetes/kubernetes/blob/93248f9ae092f571eb870b7664c534bfc7d00f03/pkg/controller/statefulset/stateful_set_control.go): updateStatefulSet, processReplica | Ordered versus parallel behavior and feature gates differ; observedGeneration can advance before readiness. |
| Batch completion | [Kubernetes v1.34.1 Job](https://github.com/kubernetes/kubernetes/blob/93248f9ae092f571eb870b7664c534bfc7d00f03/pkg/controller/job/job_controller.go): trackJobStatusAndRemoveFinalizers, manageJob | Child finalizers protect durable accounting, not only external cleanup; business retry differs from queue error backoff. |
| Scheduling | [Kubernetes v1.34.1 CronJob](https://github.com/kubernetes/kubernetes/blob/93248f9ae092f571eb870b7664c534bfc7d00f03/pkg/controller/cronjob/cronjob_controllerv2.go): syncCronJob, AlreadyExists recovery | Deterministic schedule identity repairs create-success/status-failure windows; it is not a universal exactly-once claim. |
| Direct external lifecycle | [Crossplane runtime v1.20.0 managed](https://github.com/crossplane/crossplane-runtime/blob/e4095cafe19882ad03961bb2b8b9111495517d9c/pkg/reconciler/managed/reconciler.go): ExternalCreateIncomplete, creationGracePeriod, Reconcile | Framework protocol; provider implementation still determines idempotency and observation truth. A pending marker detects ambiguity rather than making retries safe. |
| Delegated lifecycle | [Cluster API v1.11.1 Machine](https://github.com/kubernetes-sigs/cluster-api/blob/dc0fb87601071371044f60c59096ecad1b84397f/internal/controllers/machine/machine_controller.go): doReconcile, patchMachine, reconcileDelete | Provider objects and remote Nodes have different owners; continuing sub-reconcilers is safe only with explicit dependency gates. |
| Full-set projection | [ExternalDNS v0.19.0](https://github.com/kubernetes-sigs/external-dns/blob/eafce22825a6565c5f228e49bcfc117b128786a9/controller/controller.go): RunOnce; adjacent plan and TXT registry packages | Source completeness, owner IDs, deletion policy, and provider batch semantics matter; no mandatory per-source-object finalizer or For. |
| Cross-cluster distribution | [Karmada v1.15.0 execution](https://github.com/karmada-io/karmada/blob/d4402a750f6cdafdc267a638ec54ee4249a8d10b/pkg/controllers/execution/execution_controller.go): syncToClusters, handleWorkDelete; pkg/util/objectwatcher | This path can finalize after an accepted background delete. Do not cite it as confirmed remote absence or silently copy its weaker guarantee into another API. |

These are focused control-flow examples. Read relevant helpers and tests before
reusing an implementation; the table does not certify full project behavior or
cross-version compatibility.

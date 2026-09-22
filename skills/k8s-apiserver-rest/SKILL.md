---
name: k8s-apiserver-rest
description: >-
  Make an API type that already exists under pkg/apis servable by an aggregated
  Kubernetes apiserver using native compiled-in REST storage: write the
  create/update/delete strategy, the genericregistry-backed store (plus
  status/scale subresource stores), the RESTStorageProvider, and wire the group
  into the apiserver binary, then generate the clientset/listers/informers.
  Trigger when the user asks to "serve", "register", or "wire" an API
  group/resource into the apiserver, add REST storage for a Kind, or generate the
  typed client. Covers strategy, storage, RESTStorageProvider, apiserver wiring,
  and client/lister/informer codegen. Do not use for defining the API types
  themselves (that is the k8s-crd-api skill), for controller/reconcile logic,
  for CRD manifests or apiextensions-based serving, or for e2e tests.
---

# Kubernetes Apiserver REST Storage

Turn an already-defined API type (from `pkg/apis/<group>/`, produced by the
`k8s-crd-api` skill) into a resource the aggregated apiserver serves over its
API, backed directly by etcd. This is the **native compiled-in REST storage**
path — the resource is built into the apiserver binary and served like core
resources, not registered as a dynamic apiextensions CRD.

Keep hand-written storage code within `internal/apiserver/registry/**` plus the
apiserver entry/scheme wiring edits. Generated clients and, when the server
publishes schemas for compiled-in APIs, generated OpenAPI stay under
`pkg/generated/`. Do not create or modify `pkg/apis/**` types, controllers, or
CRD manifests.

## When to use

- "Make `<Kind>` servable by the apiserver" / "serve the `<group>` API group".
- "Add REST storage for `<Kind>`" / "register the `<group>` resource".
- "Wire `<group>` into the apiserver" / "generate the client for `<group>`".
- The type referenced already exists under `pkg/apis/<group>/`; if it does not,
  stop and route to the `k8s-crd-api` skill first.

## Model

The native REST storage path has four cooperating layers plus generated public outputs:

1. **Strategy** — `strategy.go` beside the resource: the object-typed REST
   semantics. It implements `rest.RESTCreateStrategy` / `RESTUpdateStrategy` /
   `RESTDeleteStrategy` (via embedded `GarbageCollectionDeleteStrategy`), decides
   namespace scope, clears/guards fields on create and update, bumps
   `Generation` on spec change, and reuses the validation package. A second
   `StatusStrategy` governs the `/status` subresource.
2. **Storage** — `storage/storage.go`: wraps `genericregistry.Store` to bind the
   strategy to an etcd-backed store, and exposes `*REST` (main resource) plus
   optional `*StatusREST` / `*ScaleREST` (subresources).
3. **RESTStorageProvider** — `rest/storage_<group>.go`: implements
   `storage.RESTStorageProvider` (`GroupName()` + `NewRESTStorage()`), which
   builds the `APIGroupInfo` and the `map[string]rest.Storage` keyed by
   `"<resource>"`, `"<resource>/status"`, `"<resource>/scale"`.
4. **Wiring** — register the provider, enable the served group-version in the
   server's resource config, and connect generated OpenAPI definitions when the
   server publishes OpenAPI. Provider registration alone is insufficient: a
   disabled group is skipped before `NewRESTStorage()` runs.

The generated **client** (`pkg/generated/clientset`, `listers`, `informers`,
`applyconfigurations`) is the typed access layer the controller consumes. It is
generated, never hand-written.

When the server publishes generated schemas, the generated **OpenAPI** package
is the discovery/schema layer consumed by `kubectl explain`, schema-aware
clients, and server-side apply tooling. Swagger-doc generation on the API types
does not replace this apiserver wiring.

## Interview rules (grill style)

1. Ask **one question at a time**; state each question's purpose and offer a
   default so the user can accept with a single keystroke.
2. Keep a **facts ledger**. Before asking, check the ledger and the repo
   (`pkg/apis/<group>/**`, `internal/apiserver/registry/**`). Never re-ask what
   the user already told you.
3. **Fast path.** If the user already supplied the group, kind, resource name,
   scope, and subresources, do not re-ask — confirm once, then write.
4. **Phase order is fixed.** Advance only after the user confirms the phase
   summary; do not jump back.
5. Match the user's language for prose; keep code identifiers in English.

## Classify the request

Decide before asking anything:

- **New group REST** — the group exists under `pkg/apis/<group>/` but has no
  `internal/apiserver/registry/<group>/` tree yet. Create the whole strategy +
  storage + `rest/` + wiring.
- **New Kind REST** — the group already has a `rest/storage_<group>.go` and other
  kinds; add strategy + storage for one more Kind and extend the provider's
  `v1<version>Storage` map.

Ask a single disambiguating question only when it is genuinely ambiguous.

## Workflow

### Phase 1 — Resource & scope

Collect, one at a time, skipping what is known:

1. group name + `<Kind>` (must already exist in `pkg/apis/<group>/`)
2. resource name: plural + singular (e.g. `aiworkloads` / `aiworkload`); ask for
   the singular only when irregular
3. scope: `namespaced` (default) vs `cluster`
4. subresources: `status` (default yes when `Status` is present), `scale`
   (only when a scale subresource is requested)

Confirm the location before proceeding.

### Phase 2 — Strategy contract

For each create/update rule, capture only what deviates from the default:

- garbage-collection policy (`rest.DeleteDependents` for dependents, or
  `rest.OrphanDependents`)
- fields cleared on create (always: `Status`; ask for any others)
- fields preserved/cleared on update (always preserve `Status`; bump
  `Generation` when spec changes)
- status updates preserve the submitted status but reset `spec` and protected
  metadata to the stored object (`metav1.ResetObjectMetaForStatus` by default)
- immutability / rejected field changes → `Validate<Kind>Update`
- validation source: reuse `pkg/apis/<group>/validation` (default) or new rules

Read `references/strategy-skeleton.md` in this phase.

### Phase 3 — Storage & subresources

Confirm the store shape and read-only surface:

- `NewFunc` / `NewListFunc` call into the internal API types
- subresources to expose (`Status`, optionally `Scale`)
- short names (only when the user asks)
- categories (only when the user asks, e.g. `all`)
- table printer handlers only when `kubectl get` table output is requested

Read `references/storage-skeleton.md` in this phase.

### Phase 4 — Register & wire

- write `rest/storage_<group>.go` (`RESTStorageProvider`: `GroupName()` +
  `NewRESTStorage()` building the `APIGroupInfo` and per-version storage map)
- edit the apiserver entry file to append
  `<group>rest.RESTStorageProvider{}` to `WithRESTStorageProviders(...)`
- ensure the group's types are registered in the apiserver scheme
  (`pkg/apis/<group>/install` `init()` + `_ import` in `import_known_versions.go`)
- confirm the resource-enabled gating (`apiResourceConfigSource.ResourceEnabled`)
  and ensure the group-version is enabled by the default resource config or by
  an explicitly documented runtime flag
- when the apiserver exposes OpenAPI, regenerate the repository's centralized
  definitions and pass their `GetOpenAPIDefinitions` entry point into the
  server configuration

Read `references/storage-skeleton.md` (provider section) in this phase.

### Phase 5 — Generate

Determine the client targets and run codegen. Read `references/codegen.md` and
`references/file-map.md`, then run or print the repository's codegen command,
and finish with a summary of written vs generated files.

## Generation rules

- Write only hand-written files. Never hand-write
  `zz_generated.*`, `generated.pb.go`, `types_swagger_doc_generated.go`, or any
  file under `pkg/generated/**` — those come from codegen tools.
- Every exported package-level type, function, and method has a doc comment
  beginning with its exact identifier. Every named struct field has a semantic
  comment.
- Reuse naming, doc phrasing, and the `legacyscheme` / serializer / printers
  plumbing from the repository's existing groups; confirm the module path from
  `go.mod` and use it (never hardcode a foreign path).
- Copy the repository's copyright boilerplate (if the repo's Go files carry one)
  from an adjacent `internal/apiserver/registry` file; do not invent a header.
- Create the group-level `internal/apiserver/registry/<group>/OWNERS` only for a
  new group and only when sibling groups use one; never create or modify a
  top-level `internal/apiserver/registry/OWNERS`.
- Run `gofmt` on everything you write.
- Produce the **complete** hand-written file set from `references/file-map.md`,
  then run every applicable client/OpenAPI codegen target and the repository's
  `verify-codegen`. Remind the user to re-run `verify-codegen` after.
- Do not expand the task beyond REST storage + enablement/OpenAPI wiring +
  generated access layers; report controller or e2e work as a follow-up instead
  of implementing it.

## Progressive loading

Load this skill in layers — never pull everything into context at once.

1. Only the `description` above is always present; it is the trigger.
2. When triggered, this SKILL.md loads. It carries the workflow only.
3. Read a reference file only when the current phase needs it, then stop.

| Phase | Read (on demand) |
|---|---|
| 1 — Resource & scope | nothing |
| 2 — Strategy contract | `references/strategy-skeleton.md` |
| 3 — Storage & subresources | `references/storage-skeleton.md` |
| 4 — Register & wire | `references/storage-skeleton.md` (provider section) |
| 5 — Generate | `references/file-map.md`, then `references/codegen.md` |

Do not pre-load all references. Load the one the phase needs and release it once
the phase is done.

---
name: k8s-controller-config
description: >-
  Author the controller-manager's component configuration: the shared overall
  config at internal/controller/apis/config/ and per-domain config trees at
  internal/controller/<group>/apis/config/ — internal + versioned types,
  register/scheme/latest, defaulting, validation, and the generated
  deepcopy/conversion/defaults files. Component config is a config-file schema,
  not a served resource. Trigger when the user asks to "add controller config",
  "component config", "controller-manager configuration", bootstrap the overall
  controller-manager config, or add a config tree for a business domain. Do not
  use for served API types (k8s-crd-api), apiserver REST storage or client
  codegen (k8s-apiserver-rest), reconciler logic (k8s-controller), or e2e tests
  (k8s-e2e).
---

# Kubernetes Controller Component Config

Author the controller-manager binary's own configuration. Component config is
what the controller-manager loads at startup — from flags and/or a config file —
before any reconciler runs. It is a **config-file schema, not a served
resource**: it never appears in apiserver discovery, has no REST storage, and is
never installed into the API scheme that serves business resources.

Two levels, both under `internal/controller/`:

1. **Shared config** — `internal/controller/apis/config/`, the overall
   controller-manager configuration: the cross-cutting generic block (leader
   election, bind addresses, parallelism, sync period, watch filter),
   infrastructure client blocks, and one top-level block per business domain.
   Written once when the framework boots; afterwards only extended.
2. **Domain config** — `internal/controller/<group>/apis/config/`, one tree per
   business domain: the domain's own knobs plus one nested block per controller
   in that domain. Created whenever a new business domain gets its first
   controller.

Both levels follow the same **versioned config convention** — the pattern used
by native component configs: an internal in-memory type (no wire tags) paired
with a versioned external type (`v1beta1`, json tags), plus defaulting,
validation, a scheme that knows both, and a `latest` facade that produces a
defaulted internal config from the versioned one. Conversion between internal
and versioned is generated, not hand-written.

Keep all output under `internal/controller/**/apis/config/**` plus the
controller-manager config-loading edit. Do not modify `pkg/apis/**`, the
apiserver registry, reconciler logic, or tests under `test/e2e/`.

## When to use

- "Bootstrap the controller-manager config" / "add the overall component config"
  (shared tree does not exist yet — rare, framework-level, one-time).
- "Add the `<group>` controller config" / "create the `<group>` config tree"
  (new business domain getting its first controller).
- "Add a config field for the `<controller>` controller" (extend an existing
  domain tree in place).
- "Wire `<group>`'s block into the overall config" (domain tree exists, overall
  config needs the top-level block).

## Model

The component-config contract, stated once:

- **Two levels, no duplication.** Cross-cutting knobs (leader election,
  parallelism, sync period, watch filter, infra clients) live in the shared
  config and in the shared generic package it embeds — never re-declared per
  domain. A domain config embeds/reuses the generic block; it adds only
  domain-specific fields.
- **Internal ⇄ versioned pair.** The internal type is what the code consumes;
  the versioned type is what the file carries. Every field exists in both, in
  the same shape; only the versioned one carries json tags and pointer-izes
  optional scalars so "unset" survives defaulting.
- **Defaulting is registered, not called ad hoc.** `SetDefaults_*` /
  `RecommendedDefault*` functions are registered in the versioned scheme; the
  only entry point is `latest.Default()` (or `scheme.Scheme.Default` on a
  decoded versioned object). Reconcilers and wiring never apply defaults
  themselves.
- **Validation runs at load.** `Validate(cfg) field.ErrorList` checks every
  constraint (concurrency ≥ 0, required image set, …); the controller-manager
  refuses to start on a non-empty list. Config validation never reaches the
  apiserver.
- **Generated files are generated.** `zz_generated.deepcopy.go`,
  `zz_generated.conversion.go`, `zz_generated.defaults.go` are produced by the
  repo's codegen script from tags in `doc.go`. Never hand-write or hand-edit
  them; never check in a config tree without running codegen.

## Interview rules (grill style)

1. Ask **one question at a time**; state each question's purpose and offer a
   default so the user can accept with a single keystroke.
2. Keep a **facts ledger**; check the ledger and repo
   (`internal/controller/**/apis/config/**`, `pkg/config/**`) before asking.
3. **Fast path.** If the user states the level (shared vs domain), the domain
   name, and the knobs each controller needs, do not re-ask — write, then
   confirm once.
4. **Phase order is fixed.** Advance only after the user confirms the phase
   summary.
5. Match the user's language for prose; keep code identifiers in English.

## Classify the request

- **Bootstrap** — `internal/controller/apis/config/` does not exist: write the
  shared tree (and nothing else; domains come later).
- **New domain** — shared tree exists, `internal/controller/<group>/apis/config/`
  does not: write the domain tree, and add the domain's top-level block to the
  shared config.
- **Extend** — the domain tree exists: add fields to the internal type, the
  versioned type, the defaulting function, and the validator, in place. Never
  recreate the tree.

Ask a single disambiguating question only when the level is genuinely ambiguous.

## Workflow

### Phase 1 — Scope & placement

Collect, one at a time, skipping what is known:

1. the level: shared (bootstrap) or `<group>` domain (new / extend)
2. the domain name and the group name string:
   `controllermanager.config.<domain>` for the shared config,
   `<group>controller.config.<domain>` for a domain config
3. the controllers in scope and, for each, its knobs (worker concurrency,
   images, client endpoints, dry-run toggles …) with proposed defaults
4. which knobs are optional scalars in the versioned type (→ pointers)

Read `references/file-map.md` in this phase.

### Phase 2 — Types

Write the internal `types.go` (no json tags; embed the generic block; nested
per-controller blocks) and the mirrored `v1beta1/types.go` (json tags,
pointers for optional scalars, `+optional` comments). Every field exists at
both levels.

Read `references/shared-config-skeleton.md` (bootstrap) or
`references/group-config-skeleton.md` (domain) in this phase.

### Phase 3 — Register & scheme

Write `register.go` (internal, `runtime.APIVersionInternal`), `v1beta1/register.go`
(external version + `addDefaultingFuncs` + `localSchemeBuilder` init), and
`scheme/scheme.go` (registers both levels, exposes Scheme + Codecs).

Read the same skeleton's register/scheme section in this phase.

### Phase 4 — Defaulting & latest

Write `v1beta1/defaults.go` (`SetDefaults_*` delegating to
`RecommendedDefault*` per nested block) and `latest/latest.go`
(`Default()` → versioned → `scheme.Scheme.Default` → convert to internal).

Read the same skeleton's defaults/latest section in this phase.

### Phase 5 — Validation

Write `validation/validation.go`: one `Validate<...>Configuration` per block,
`field.ErrorList`, children addressed through `field.NewPath(...)`.

Read the same skeleton's validation section in this phase.

### Phase 6 — Codegen & consumption

Tag `doc.go` (`+k8s:deepcopy-gen=package`, `+groupName=<...>`), run the repo's
codegen script to produce the `zz_generated.*` files, add `OWNERS`, and wire
consumption: the controller-manager entry loads the config via
`latest.Default()` + decode + `Validate`; each reconciler receives only its own
nested block (`ComponentConfig`).

Read `references/file-map.md` (generated-file list and wiring edits) and the
skeleton's codegen/consumption section in this phase.

## Rules

- Config types are never served: no apiserver registration, no REST storage, no
  discovery entry, no printers. If the user asks for that, stop — it is a
  served-resource task (k8s-crd-api / k8s-apiserver-rest).
- Write only hand-written files. `zz_generated.*` files come from codegen; if a
  script run is impossible in the environment, leave them missing and say so —
  do not hand-write them.
- Reuse the shared generic block from `pkg/config/**`; a domain config embeds
  it, never re-declares its fields.
- Every exported identifier gets an identifier-first doc comment; every named
  struct field a semantic comment.
- Every config package root gets an `OWNERS` file.
- Run `gofmt` on everything you write.
- Do not expand the task into reconciler logic; report reconciler/registration
  work as a follow-up (k8s-controller).

## Progressive loading

1. Only the `description` above is always present; it is the trigger.
2. When triggered, this SKILL.md loads; it carries the workflow.
3. Read a reference only when the current phase needs it, then stop.

| Phase | Read (on demand) |
|---|---|
| 1 — Scope & placement | `references/file-map.md` |
| 2 — Types | `references/shared-config-skeleton.md` or `references/group-config-skeleton.md` |
| 3 — Register & scheme | the same skeleton (register/scheme section) |
| 4 — Defaulting & latest | the same skeleton (defaults/latest section) |
| 5 — Validation | the same skeleton (validation section) |
| 6 — Codegen & consumption | `references/file-map.md`, the same skeleton (codegen/consumption section) |

Do not pre-load all references.

---
name: k8s-crd-api
description: >-
  Create or modify Kubernetes-style API packages under pkg/apis using an
  internal/external version split. Trigger when the user asks to scaffold an API
  group, add a Kind to an existing group, define Spec/Status fields, or turn a
  pasted API definition into internal and versioned Go types. Covers API types,
  scheme registration, install wiring, validation, defaulting, conditions, and
  codegen metadata within pkg/apis. Do not use for generic Kubebuilder CRDs, CRD
  manifests, apiserver REST registry or storage, controllers, or webhooks.
---

# Kubernetes API Package Engineering

Generate Kubernetes-style API code under `pkg/apis/` using internal and external
versions. This is not a generic Kubebuilder/controller-runtime CRD scaffolder.
Inspect the target repository and preserve its local package and codegen
conventions.

Keep all hand-written output within `pkg/apis/**`. Do not create or modify
apiserver REST registry/storage, controllers, webhook implementations, or CRD
manifests.

## When to use

- "Create a new API group" (e.g. `ai.example.io`).
- "Add a Kind to an existing group" (e.g. add `AIWorkload` to
  `ai.example.io/v1alpha1`).
- The user pastes a complete API or Go type definition and wants it turned into
  internal and versioned API packages.

## Model

Use the hub-and-spoke multi-version model:

- **internal** version (`runtime.APIVersionInternal`) — the canonical, in-process
  form used by controllers and runtime validation.
- **external** version (`v1alpha1` / `v1beta1` / `v1`) — the versioned wire form.
  Scheme defaulting is registered here.
- Generate mechanical conversion between matching representations. If the two
  versions differ semantically, stop and report the need for a reviewed manual
  conversion instead of forcing generated conversion.

Layout:

```
pkg/apis/<group>/               # internal (package <group>)
pkg/apis/<group>/<version>/     # external (package <version>)
pkg/apis/<group>/install/       # installer
pkg/apis/<group>/validation/    # hand-written validation
```

## Interview rules (grill style)

1. Ask **one question at a time**; state each question's purpose and offer a
   default so the user can accept with a single keystroke.
2. Keep a **facts ledger**. Before asking, check the ledger and the repo
   (`pkg/apis/**`). Never re-ask what the user already told you.
3. **Fast path.** If the user already supplied a complete field definition
   (full YAML/Go), do not re-ask — convert directly, then do one confirmation.
4. **Phase order is fixed.** Advance only after the user confirms the phase
   summary; do not jump back.
5. Match the user's language for prose; keep code identifiers in English.

## Classify the request

Decide before asking anything:

- **New Group** — the group is not under `pkg/apis/` and the user is creating
  one.
- **New Kind** — the group already exists (directory present or `GroupName`
  already registered).
- Ask a single disambiguating question only when it is genuinely ambiguous.

## Workflow

### Phase 1 — Resource location

Collect, one at a time, skipping what is known:

1. group name + domain → `GroupName = <name>.<domain>`
2. version (default `v1alpha1` for a new API)
3. Kind name (UpperCamelCase) — for a new Group, the first Kind
4. scope (default `namespaced`)
5. owners — new Group only; read `pkg/apis/OWNERS` and neighboring group
   OWNERS files as read-only conventions, then create only
   `pkg/apis/<group>/OWNERS` when sibling groups use one. Never create or modify
   the top-level `pkg/apis/OWNERS`.

Confirm the location before proceeding.

### Phase 2 — Spec

Ask for Spec fields. Allow a bulk list, then drill into ambiguous fields one at
a time. For each field capture: name, Go type, JSON name, required/optional,
default, enum, one-line description. Skip anything already supplied.

### Phase 3 — Status

Offer standard status fields as defaults (`ObservedGeneration`, `Conditions`)
and ask which are needed, plus optional `FailureReason`/`FailureMessage`,
`Phase`, and resource references. When Phase is selected, collect every value
and a distinct semantic description for each value; do not infer undocumented
constants.

### Phase 4 — Conditions

Ask whether the resource needs Conditions; collect ConditionTypes (offer
`Ready`) and Reasons. Capture the meaning of every exported ConditionType and
Reason, including false-condition severity where applicable. If none, skip.

### Phase 5 — Validation & defaults

Map each rule to its layer:

- field format (enum / pattern / min / max) → schema markers for documentation
  and generation, plus `validation/` when the API server must enforce it
- object, update, status, and cross-field rules → `validation/` package
- default values → `defaults.go`
- rules that must be enforced at runtime → `validation/` package

Read `references/validation-defaulting.md` in this phase.

### Phase 6 — Generate

Determine the file set (`references/file-map.md`), write the hand-written files
using the byte-level templates (`references/field-templates.md`,
`references/group-skeleton.md`), then run or print codegen commands
(`references/codegen.md`). Add the group-level fuzzer and round-trip coverage
described in `references/testing.md`. Finish with a summary of what was written
vs generated.

## Generation rules

- Write only hand-written files. Never hand-write `zz_generated.*` (deepcopy,
  conversion, defaults), `generated.pb.go`, `types_swagger_doc_generated.go`, or
  client/lister/informer code — those come from codegen tools.
- Every exported package-level type, constant, variable, function, and method
  has a doc comment beginning with its exact identifier. Every named API struct
  field has a semantic comment; fixed Kubernetes metadata/spec/status phrases
  in the templates are intentional exceptions to identifier-first wording.
- Use the exact standard comment phrases and `More info:` links from
  `references/field-templates.md`.
- Copy the repository's copyright boilerplate and package import-comment style
  from adjacent `pkg/apis` files; do not invent a new header.
- Treat `pkg/apis/OWNERS` as read-only inherited policy. This skill may create
  or edit only `pkg/apis/<group>/OWNERS`, and only when the task is a new group
  or the user explicitly asks to change group ownership.
- Run `gofmt` on everything you write; do not hand-align struct tags.
- Run `go run <skill>/scripts/check-exported-docs.go -- <written .go files>`
  before codegen. Fix every finding in hand-written files.
- Emit the codegen commands (or run them if the repo has a script) and remind
  the user to run `verify-codegen` after.
- Do not expand the task beyond `pkg/apis/**`; report any required integration
  work outside that tree as a follow-up instead of implementing it.

## Progressive loading

Load this skill in layers — never pull everything into context at once.

1. Only the `description` above is always present; it is the trigger.
2. When triggered, this SKILL.md loads. It carries the workflow only. The
   templates and skeletons in `references/` are not loaded yet.
3. Read a reference file only when the current phase needs it, then stop.

| Phase | Read (on demand) |
|---|---|
| 1 — Resource location | nothing |
| 2 — Spec / 3 — Status | `references/field-templates.md` |
| 4 — Conditions | `references/group-skeleton.md` |
| 5 — Validation & defaults | `references/validation-defaulting.md` |
| 6 — Generate | `references/file-map.md`, then only the templates needed from `references/field-templates.md` / `references/group-skeleton.md`, then `references/testing.md` and `references/codegen.md` |

Do not pre-load all references. Load the one the phase needs and release it once
the phase is done.

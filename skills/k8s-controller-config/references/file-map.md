# File map per scenario

## Scenario A — bootstrap the shared (overall) config

Write:

```
internal/controller/apis/config/doc.go                    # package doc + +k8s:deepcopy-gen=package + +groupName tags
internal/controller/apis/config/types.go                  # internal ControllerManagerConfiguration (no json tags)
internal/controller/apis/config/register.go               # internal SchemeGroupVersion (APIVersionInternal) + AddToScheme
internal/controller/apis/config/scheme/scheme.go          # Scheme + Codecs; registers internal + v1beta1
internal/controller/apis/config/latest/latest.go          # latest.Default() -> defaulted internal config
internal/controller/apis/config/validation/validation.go  # Validate(cfg) field.ErrorList
internal/controller/apis/config/OWNERS                    # group-level owners
internal/controller/apis/config/v1beta1/doc.go
internal/controller/apis/config/v1beta1/types.go          # external type (json tags, pointer optionals)
internal/controller/apis/config/v1beta1/defaults.go       # SetDefaults_* + RecommendedDefault*
internal/controller/apis/config/v1beta1/register.go       # external GroupName/Version + addDefaultingFuncs
internal/controller/apis/config/v1beta1/conversion.go      # OPTIONAL hand-written conversion helpers
```

Hand-written `conversion.go` goes in only when a field needs custom
internal⇄versioned conversion beyond what `zz_generated.conversion.go` covers
(for example a field intentionally dropped during conversion). Omit it
otherwise.

Generated (never hand-written) alongside:

```
internal/controller/apis/config/zz_generated.deepcopy.go
internal/controller/apis/config/v1beta1/zz_generated.deepcopy.go
internal/controller/apis/config/v1beta1/zz_generated.defaults.go
internal/controller/apis/config/v1beta1/zz_generated.conversion.go
```

Edit the wiring:

- the controller-manager entry (`cmd/<...>-controller-manager/` or its app
  package) — load the config: flags/config-file → decode versioned →
  `latest.Default()` → `Validate` → completed config consumed by the manager.
- the options/config-loading layer — retain every domain block from defaults,
  replace it when a config file is decoded, copy it into the final internal
  `ComponentConfig`, and validate the final flag/options-assembled config.

Add focused tests proving that unset optional scalars receive defaults,
explicit zero values survive decode/default/convert, invalid values prevent
startup, and each domain block reaches the final `ComponentConfig`.

Bootstrap happens once per project; afterwards the shared tree is only
**extended** (new domain block), never recreated.

## Scenario B — new domain config tree

Write (all under the domain's tree):

```
internal/controller/<group>/apis/config/doc.go                    # +k8s:deepcopy-gen=package + +groupName=<group>controller.config.<domain>
internal/controller/<group>/apis/config/types.go                  # internal <Group>ControllerConfiguration (no json tags)
internal/controller/<group>/apis/config/register.go               # internal SchemeGroupVersion + AddToScheme
internal/controller/<group>/apis/config/scheme/scheme.go          # Scheme + Codecs; registers internal + v1beta1
internal/controller/<group>/apis/config/latest/latest.go          # latest.Default() -> defaulted internal domain config
internal/controller/<group>/apis/config/validation/validation.go  # per-block Validate field.ErrorList
internal/controller/<group>/apis/config/OWNERS
internal/controller/<group>/apis/config/v1beta1/doc.go
internal/controller/<group>/apis/config/v1beta1/types.go          # external type (json tags, pointer optionals)
internal/controller/<group>/apis/config/v1beta1/defaults.go       # SetDefaults_<Group>ControllerConfiguration
internal/controller/<group>/apis/config/v1beta1/register.go       # external GroupName/Version + addDefaultingFuncs
internal/controller/<group>/apis/config/v1beta1/conversion.go      # OPTIONAL hand-written conversion helpers
```

Hand-written `conversion.go` is optional — see Scenario A.

Generated (never hand-written):

```
internal/controller/<group>/apis/config/zz_generated.deepcopy.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.deepcopy.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.defaults.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.conversion.go
```

Edit the wiring:

- `internal/controller/apis/config/types.go` (+ `v1beta1/types.go`,
  `v1beta1/defaults.go`, `validation/validation.go`) — add the domain's
  top-level block as a **locally declared mirror type** with the domain's
  fields. Never type the field as the domain tree's own config types:
  conversion generators cannot convert nested fields across config groups.
- the controller-manager entry — load the domain config the same way
  (versioned → default → convert → validate) and pass each controller's nested
  block to its reconciler. Reconciler construction itself is out of scope
  (k8s-controller).
- the shared options/config-loading path — retain the locally mirrored block
  across defaults, file loading, and final `ComponentConfig` assembly.

The shared mirror's versioned optional scalars use pointers exactly as the
domain version does. Test both trees for unset defaults and explicit zero-value
preservation, then test the shared file-to-runtime path.

## Scenario C — extend an existing domain tree

Edit, in place:

```
internal/controller/<group>/apis/config/types.go                  # add field(s) to internal type
internal/controller/<group>/apis/config/v1beta1/types.go          # mirror field(s) with json tags
internal/controller/<group>/apis/config/v1beta1/defaults.go       # default the new field(s)
internal/controller/<group>/apis/config/validation/validation.go  # validate the new field(s)
```

Then re-run codegen so `zz_generated.deepcopy.go` /
`zz_generated.conversion.go` pick up the new fields. Do **not** recreate the
tree; do not add a second versioned package (bump only when the config's wire
compatibility actually breaks).

Extend the existing defaulting, validation, decode, and options-propagation
tests for every newly added knob.

## Shared vs domain config

| Config | Path | Purpose |
|---|---|---|
| shared | `internal/controller/apis/config/` | leader election, bind addresses, parallelism, sync period, watch filter, infra clients, one top-level block per domain |
| domain | `internal/controller/<group>/apis/config/` | the domain's own knobs + one nested block per controller in the domain |

The two levels never import each other's types. A domain tree embeds the
generic block (`pkg/config/**` or wherever the repo keeps it) only when the
domain loads a standalone config file; in a single-binary repo it carries
domain knobs only. When the overall config file must carry the domain's
knobs, the shared config declares a local mirror of the domain's block.

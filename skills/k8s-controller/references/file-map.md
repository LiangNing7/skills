# File map per scenario

## Scenario A — new controller group (config + first reconciler)

Write:

```
internal/controller/<group>/<controller>/doc.go                    # package doc: what it reconciles + owns
internal/controller/<group>/<controller>/controller.go             # Reconciler + SetupWithManager + Reconcile
internal/controller/<group>/<controller>/<controller>_phases.go    # one file per reconcile phase (if several)
internal/controller/<group>/<controller>/<controller>_status_condition_utils.go  # condition consts + condition updater
internal/controller/<group>/<controller>/<controller>_test.go      # unit tests

internal/controller/<group>/apis/config/doc.go
internal/controller/<group>/apis/config/types.go                   # internal config type (no json tags)
internal/controller/<group>/apis/config/register.go                # internal SchemeGroupVersion + AddToScheme
internal/controller/<group>/apis/config/scheme/scheme.go           # runtime scheme for Default() + Convert()
internal/controller/<group>/apis/config/latest/latest.go           # latest.Default() -> internal with defaults
internal/controller/<group>/apis/config/validation/validation.go   # Validate(cfg) field.ErrorList
internal/controller/<group>/apis/config/v1beta1/doc.go
internal/controller/<group>/apis/config/v1beta1/types.go           # external config type (json tags)
internal/controller/<group>/apis/config/v1beta1/defaults.go        # SetDefaults_<Config> + RecommendedDefault*
internal/controller/<group>/apis/config/v1beta1/register.go        # external GroupName/Version + addDefaultingFuncs
```

Generated (never hand-written) alongside the config package:

```
internal/controller/<group>/apis/config/zz_generated.deepcopy.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.deepcopy.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.defaults.go
internal/controller/<group>/apis/config/v1beta1/zz_generated.conversion.go
```

Edit the registration wiring:

- `internal/controller/names/...` (or the repo's canonical-names package) — add the
  controller name constant.
- the controller-manager entry that runs `setupReconcilers` / the descriptor map —
  add a block building this reconciler with its `ComponentConfig` and registering
  it.

The **shared** config (`internal/controller/apis/config/`) already exists and is
reused, not recreated.

## Scenario B — new reconciler / new logic in an existing group

Write / edit:

```
internal/controller/<group>/<controller>/doc.go            # new
internal/controller/<group>/<controller>/controller.go     # new
internal/controller/<group>/<controller>/<controller>_*.go # new, per phase
internal/controller/<group>/<controller>/<controller>_test.go  # new
internal/controller/names/...                              # edit: add name constant
<controller-manager entry>                                  # edit: register the reconciler
```

Do **not** recreate the group's `apis/config/` tree unless new config fields are
required; extend `types.go`/`v1beta1/types.go`/`defaults.go` in place instead.

## Shared vs group config

| Config | Path | Purpose |
|---|---|---|
| shared | `internal/controller/apis/config/` | leader election, bind addresses, parallelism, sync period, watch filter, `Controllers` list |
| group | `internal/controller/<group>/apis/config/` | group-specific flags + nested per-controller blocks |

The group config embeds/reuses the shared generic block; it never duplicates the
cross-cutting knobs.
# File map per scenario

## Scenario A — new Group + first Kind

Write:

```
pkg/apis/<group>/doc.go                        # internal markers
pkg/apis/<group>/register.go                   # internal, APIVersionInternal
pkg/apis/<group>/<kind>_types.go
pkg/apis/<group>/condition_types.go            # if conditions
pkg/apis/<group>/common_types.go               # if shared constants/types
pkg/apis/<group>/OWNERS

pkg/apis/<group>/<version>/doc.go              # external markers
pkg/apis/<group>/<version>/register.go         # external, + addDefaultingFuncs
pkg/apis/<group>/<version>/<kind>_types.go
pkg/apis/<group>/<version>/condition_types.go  # if conditions
pkg/apis/<group>/<version>/condition_consts.go # if conditions
pkg/apis/<group>/<version>/defaults.go         # if defaults

pkg/apis/<group>/install/install.go + doc.go
pkg/apis/<group>/validation/validation_<kind>.go  # if cross-field validation
```

Then run codegen (deepcopy / conversion / defaulter / openapi).

## Scenario B — new Kind in an existing Group

Write / edit:

```
pkg/apis/<group>/<kind>_types.go                    # new, internal
pkg/apis/<group>/register.go                        # edit: append to addKnownTypes
pkg/apis/<group>/<version>/<kind>_types.go          # new, external
pkg/apis/<group>/<version>/register.go              # edit: append to addKnownTypes
pkg/apis/<group>/<version>/defaults.go              # edit/new: SetDefaults_*
pkg/apis/<group>/<version>/condition_consts.go      # edit: append ConditionType/Reason
pkg/apis/<group>/validation/validation_<kind>.go    # edit/new
```

Do **not** recreate `doc.go`, `install/`, or `OWNERS` for an existing group.

Then run codegen.

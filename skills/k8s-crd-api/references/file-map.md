# File map per scenario

## Scenario A — new Group + first Kind

Every file below is required unless explicitly marked conditional (`# if ...`).
`defaults.go` is always required — its `SetDefaults_*` body may be empty when no
field has a default.

Write:

```
pkg/apis/<group>/doc.go                        # internal markers
pkg/apis/<group>/register.go                   # internal, APIVersionInternal
pkg/apis/<group>/<kind>_types.go
pkg/apis/<group>/<kind>_phase_types.go      # if Status.Phase is used
pkg/apis/<group>/condition_types.go            # if conditions
pkg/apis/<group>/common_types.go               # if shared constants/types
pkg/apis/<group>/well_known_annotations.go     # if group-level annotation keys
pkg/apis/<group>/well_known_labels.go          # if group-level label keys
pkg/apis/<group>/OWNERS                     # new group only, if siblings use it; never pkg/apis/OWNERS

pkg/apis/<group>/<version>/doc.go              # external markers
pkg/apis/<group>/<version>/register.go         # external, + addDefaultingFuncs
pkg/apis/<group>/<version>/<kind>_types.go
pkg/apis/<group>/<version>/<kind>_phase_types.go # if Status.Phase is used
pkg/apis/<group>/<version>/condition_types.go  # if conditions
pkg/apis/<group>/<version>/condition_consts.go # if conditions
pkg/apis/<group>/<version>/defaults.go         # always; SetDefaults_* may be empty

pkg/apis/<group>/install/install.go + doc.go
pkg/apis/<group>/install/roundtrip_test.go
pkg/apis/<group>/fuzzer/doc.go + fuzzer.go
pkg/apis/<group>/validation/validation_<kind>.go
pkg/apis/<group>/validation/validation_<kind>_test.go
```

Group-level annotation and label keys go in `well_known_annotations.go` /
`well_known_labels.go` when the repository splits them out; otherwise put them
in `common_types.go`.

Create validation files only when the resource has enforceable rules, but do not
omit object metadata validation from a served resource. Then run the applicable
codegen targets.

## Scenario B — new Kind in an existing Group

Write / edit:

```
pkg/apis/<group>/<kind>_types.go                    # new, internal
pkg/apis/<group>/<kind>_phase_types.go              # if Status.Phase is used
pkg/apis/<group>/register.go                        # edit: append to addKnownTypes
pkg/apis/<group>/<version>/<kind>_types.go          # new, external
pkg/apis/<group>/<version>/<kind>_phase_types.go    # if Status.Phase is used
pkg/apis/<group>/<version>/register.go              # edit: append to addKnownTypes
pkg/apis/<group>/<version>/defaults.go              # edit/new: SetDefaults_*
pkg/apis/<group>/<version>/condition_consts.go      # edit: append ConditionType/Reason
pkg/apis/<group>/validation/validation_<kind>.go    # edit/new
pkg/apis/<group>/validation/validation_<kind>_test.go # edit/new
pkg/apis/<group>/fuzzer/fuzzer.go                   # edit when custom normalization is needed
pkg/apis/<group>/install/roundtrip_test.go           # normally reused; ensure the new Kind is covered
```

Do **not** recreate `doc.go`, `install/`, or `OWNERS` for an existing group.

Do not create a second round-trip test for each Kind: the group-level test uses
scheme registration to discover all registered objects. Then run codegen.

# File map per scenario

## Scenario A — new group REST (first Kind in the group)

Every file below is required unless explicitly marked conditional
(`# if ...`). `strategy.go` and `storage/storage.go` are always required.

Write:

```
internal/apiserver/registry/<group>/<kind>/doc.go        # package doc + import comment
internal/apiserver/registry/<group>/<kind>/strategy.go   # create/update/delete + status strategy, matcher
internal/apiserver/registry/<group>/<kind>/strategy_test.go # status boundary + generation behavior
internal/apiserver/registry/<group>/<kind>/storage/doc.go
internal/apiserver/registry/<group>/<kind>/storage/storage.go  # genericregistry.Store + subresource stores
internal/apiserver/registry/<group>/rest/doc.go
internal/apiserver/registry/<group>/rest/storage_<group>.go   # RESTStorageProvider
internal/apiserver/registry/<group>/OWNERS               # new group only, if sibling groups use one
```

Edit the apiserver entry file (the function that assembles `ServerRunOptions`) to
append `<group>rest.RESTStorageProvider{}` to the `WithRESTStorageProviders(...)`
call. The block resembles:

```go
opts, err := ...,
	app.WithRESTStorageProviders(
		<group>rest.RESTStorageProvider{},
	),
```

Register the group's types into the apiserver's process-wide scheme so the
storage layer can encode/decode them: ensure `pkg/apis/<group>/install` registers
into the scheme via `init()` (see the `k8s-crd-api` skill), and `_ import` that
install package from the apiserver's `import_known_versions.go`:

```go
// import_known_versions.go
import (
	_ "<module>/pkg/apis/<group>/install"
)
```

Provider registration does not enable a group-version. Follow the repository's
resource-config convention and either enable `<group>/<version>` by default or
document and test the runtime flag that enables it. Add a focused test against
the effective `APIResourceConfigSource`; otherwise the install loop may skip
the group before the provider is invoked.

Generated (never hand-written), written under `pkg/generated/`:

```
pkg/generated/clientset/...          # client-gen
pkg/generated/listers/...            # lister-gen
pkg/generated/informers/...          # informer-gen
pkg/generated/applyconfigurations/...  # applyconfiguration-gen   (only if clientset is generated)
pkg/generated/openapi/...              # openapi-gen, when the server publishes compiled-in schemas
```

When centralized OpenAPI is present, regenerate it and wire its
`GetOpenAPIDefinitions` function into the apiserver entry/config. A package-level
Swagger-doc file does not by itself publish the resource in `/openapi/v2` or
`/openapi/v3`.

Add a table-printer handler (under `internal/pkg/printers/...`) only when
`kubectl get` table output is requested; it powers the store's
`TableConvertor` and is otherwise optional.

## Scenario B — new Kind REST in an existing group

Write / edit:

```
internal/apiserver/registry/<group>/<kind>/doc.go            # new
internal/apiserver/registry/<group>/<kind>/strategy.go       # new
internal/apiserver/registry/<group>/<kind>/strategy_test.go  # new
internal/apiserver/registry/<group>/<kind>/storage/doc.go    # new
internal/apiserver/registry/<group>/<kind>/storage/storage.go # new
internal/apiserver/registry/<group>/rest/storage_<group>.go  # edit: add the storage block to the version map
```

Do **not** recreate `rest/doc.go` for an existing group. Extend the existing
`RESTStorageProvider`'s per-version storage map with the new `"<resource>"` and
`"<resource>/status"` entries instead of writing a new provider. Do not recreate
the group-level `OWNERS` for an existing group either.

If this Kind adds new wire types, regenerate the centralized OpenAPI output when
the repository has one; do not add a second OpenAPI provider for the group.

## Subresource surface (status / scale)

| Subresource | Store field | Strategy | Enabled when |
|---|---|---|---|
| none | `*REST` | `Strategy` | always |
| `status` | `*StatusREST` | `StatusStrategy` | `Status` field present (default) |
| `scale` | `*ScaleREST` | scale getter/update | a scale subresource is explicitly requested |

The provider's storage map keys each subresource separately:
`"<resource>"`, `"<resource>/status"`, and (if scale) `"<resource>/scale"`.

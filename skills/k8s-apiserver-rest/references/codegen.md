# Client / lister / informer codegen

The typed access layer is generated, never hand-written. It lives under
`pkg/generated/` and is produced by the repository's codegen script
(`scripts/update-codegen.sh` or equivalent `Makefile`/`hack` target).

## Hand-written vs generated

| File | Owner |
|---|---|
| strategy / storage / provider / wiring | **hand-written (you write)** |
| `pkg/generated/clientset/...` | `client-gen` |
| `pkg/generated/listers/...` | `lister-gen` |
| `pkg/generated/informers/...` | `informer-gen` |
| `pkg/generated/applyconfigurations/...` | `applyconfiguration-gen` |
| `pkg/generated/openapi/...` | `openapi-gen` (repository-wide; required when the apiserver publishes compiled-in schemas) |

The API-type codegen (deepcopy / conversion / defaulter / protobuf /
swagger-doc) is the `k8s-crd-api` skill's concern and should already be done;
this skill generates the client-facing layer and, when centrally published by
the apiserver, the repository-wide OpenAPI package.

## What to generate

| Tier | Artifact | Generator |
|---|---|---|
| **Generate** | `clientset` | `client-gen` |
| | `listers` | `lister-gen` |
| | `informers` | `informer-gen` |
| **Generate alongside clientset** | `applyconfigurations` | `applyconfiguration-gen` |
| **Generate when centrally served** | `openapi` | `openapi-gen` |
| **Skip** | types-level codegen (already in `pkg/apis`) | — |

`client-gen` requires `+genclient` on the type and `+genclient:nonNamespaced`
for cluster-scoped kinds; these markers live in the versioned types and are
written by the `k8s-crd-api` skill. Verify they are present before running.

## Execution strategy

1. Detect the repository codegen script and its target names. The common shape:

```bash
scripts/update-codegen.sh client lister informer applyconfiguration
```

   Read the target names from the repository's own script; the example above is
   illustrative, not authoritative.
2. Prefer focused targets that emit `pkg/generated/**` only. Include the
   repository's OpenAPI target when the apiserver exposes generated definitions.
   Do not re-run types-level targets (deepcopy / conversion / protobuf) unless
   the types changed in this task.
3. Confirm the output package root from the script's `OUTPUT_PKG`
   (`<module>/pkg/generated`) and keep generated files under it. Never move or
   hand-edit generated output.
4. Run `gofmt` on any hand-written file and the repository's `verify-codegen`
   command afterward; it enforces that committed generated output matches a
   fresh run.

Some `verify-codegen` wrappers require a clean worktree. Do not skip
verification because the implementation is still uncommitted: verify from an
equivalent clean temporary worktree/synthetic commit, or run it immediately
after making the intended commit. If neither is possible, rerun the exact
generation targets and compare generated-file hashes, and disclose that
fallback.

## Consumption (for the controller)

The controller consumes this layer: `pkg/generated/clientset` for typed
REST calls and `pkg/generated/informers` (+ `listers`) for cache-backed watch
and reads. This is the `k8s-controller` skill's starting point; this skill only
produces it.

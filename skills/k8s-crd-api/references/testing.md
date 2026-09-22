# API package verification

Read this reference only when generating or verifying files in Phase 6.

## Hand-written checks

1. Run `gofmt` on every written Go file.
2. Run the skill's exported-documentation checker on only the files written or
   edited in this task:

   ```bash
   go run <skill-dir>/scripts/check-exported-docs.go -- <written-go-files...>
   ```

3. Run focused validation/defaulting tests, then `go test ./pkg/apis/...` when
   the repository can build that package tree independently.

Status validation tests should exercise semantic invariants, not merely call an
empty validator: cover phase domains, associative-condition key uniqueness,
condition status/severity rules, observed-generation bounds, and exact field
paths.

The documentation checker intentionally does not scan the entire repository:
older API packages may contain known historical violations, while newly written
declarations must not add more.

## Fuzzer

Each API group has a `fuzzer/` package used by scheme round-trip tests. Add
custom fuzzer functions only for values that generic random filling cannot keep
consistent with defaulting or conversion invariants. A custom function should:

- call `FillNoCustom` to avoid recursion;
- initialize pointer fields that internal types require to be non-nil;
- choose typed enum values from the declared set;
- normalize values exactly as defaulting/conversion expects.

Do not add a custom fuzzer merely to make an invalid business object pass
validation; round-trip testing verifies serialization/conversion, not admission.

## Round-trip test

Keep one group-level test under `install/roundtrip_test.go`:

```go
func TestRoundTripTypes(t *testing.T) {
	roundtrip.RoundTripTestForAPIGroup(t, Install, groupfuzzer.Funcs)
}
```

Because the test discovers registered runtime objects from the installed
scheme, adding a Kind to both `addKnownTypes` functions makes it part of this
test automatically. A failure commonly indicates mismatched internal/external
fields, missing conversion, an invalid protobuf tag, or incomplete fuzzer
normalization.

## Codegen verification

After generation, run the repository's `verify-codegen` command when available.
Review the diff: generated output is evidence that markers and tags were
consumed, not permission to accept unrelated changes outside `pkg/apis/**`.

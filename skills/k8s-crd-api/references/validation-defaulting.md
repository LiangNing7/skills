# Validation and defaulting

Read this reference only during Phase 5. Runtime validation uses internal types;
scheme defaulting uses external versioned types.

## Rule placement

| Rule | Required location |
|---|---|
| enum, format, min/max, pattern used for schema documentation | field marker |
| any rule the API server must reject at runtime | internal `validation/` |
| create/update immutability or cross-field relationship | internal `validation/` |
| status-transition rule | internal status validation |
| wire default | external `<version>/defaults.go` |

Markers do not replace runtime validation. Add both when a constraint must be
visible in OpenAPI and enforced by the API server.

## Validation shape

Use `field.ErrorList`, precise `field.Path` values, and internal API types. A
served namespaced resource normally validates metadata as well as its spec:

```go
// Validate<Kind>Name validates names used by <Kind> objects.
var Validate<Kind>Name = apimachineryvalidation.NameIsDNSSubdomain

// Validate<Kind> validates a new <Kind>.
func Validate<Kind>(obj *<group>.<Kind>) field.ErrorList {
	allErrs := corevalidation.ValidateObjectMeta(
		&obj.ObjectMeta,
		true,
		Validate<Kind>Name,
		field.NewPath("metadata"),
	)
	allErrs = append(allErrs, Validate<Kind>Spec(&obj.Spec, field.NewPath("spec"))...)
	return allErrs
}

// Validate<Kind>Spec validates a <Kind> spec.
func Validate<Kind>Spec(spec *<group>.<Kind>Spec, fldPath *field.Path) field.ErrorList {
	allErrs := field.ErrorList{}
	// Append field.Required, field.Invalid, field.NotSupported, or field.Forbidden.
	return allErrs
}

// Validate<Kind>Update validates an update to a <Kind>.
func Validate<Kind>Update(obj, old *<group>.<Kind>) field.ErrorList {
	allErrs := corevalidation.ValidateObjectMetaUpdate(
		&obj.ObjectMeta,
		&old.ObjectMeta,
		field.NewPath("metadata"),
	)
	allErrs = append(allErrs, Validate<Kind>SpecUpdate(&obj.Spec, &old.Spec, field.NewPath("spec"))...)
	return allErrs
}

// Validate<Kind>SpecUpdate validates an update to a <Kind> spec.
func Validate<Kind>SpecUpdate(spec, old *<group>.<Kind>Spec, fldPath *field.Path) field.ErrorList {
	allErrs := Validate<Kind>Spec(spec, fldPath)
	// Add immutability and transition checks against old.
	return allErrs
}

// Validate<Kind>Status validates a <Kind> status.
func Validate<Kind>Status(status *<group>.<Kind>Status, fldPath *field.Path) field.ErrorList {
	allErrs := field.ErrorList{}
	// If present, validate Phase against every declared phase value.
	// Validate ObservedGeneration bounds and each Condition's type, status,
	// severity contract, and uniqueness by the list-map key.
	return allErrs
}

// Validate<Kind>StatusUpdate validates a status update to a <Kind>.
func Validate<Kind>StatusUpdate(obj, old *<group>.<Kind>) field.ErrorList {
	allErrs := corevalidation.ValidateObjectMetaUpdate(
		&obj.ObjectMeta,
		&old.ObjectMeta,
		field.NewPath("metadata"),
	)
	allErrs = append(allErrs, Validate<Kind>Status(&obj.Status, field.NewPath("status"))...)
	return allErrs
}
```

Adapt pointer/value signatures to the neighboring validation package. Do not
emit empty placeholder functions when the group centralizes several Kinds in a
single `validation.go`; extend the established organization instead.

Status fields carry API contracts just like spec fields. When the status type
declares any of the following, enforce them in `Validate<Kind>Status`:

- typed phase: empty only when documented, otherwise one of the declared values;
- `ObservedGeneration`: non-negative and, on status update, not greater than
  the object's current `metadata.generation`;
- conditions: non-empty and syntactically valid map keys, unique condition
  types, a valid condition status, and any documented status/severity rule.

`Validate<Kind>StatusUpdate` must call `ValidateObjectMetaUpdate` even when the
status strategy resets protected metadata. The strategy protects authorization
boundaries; validation still enforces update metadata invariants and precise
error paths.

## Defaulting shape

`defaults.go` (with `addDefaultingFuncs` and `SetDefaults_*`) is a permanent part
of the versioned package, even when no field has a default — in that case
`SetDefaults_*` is simply empty. Do not omit the file.

Default external versioned objects so decoding and conversion enter the hub
with normalized values:

```go
func addDefaultingFuncs(scheme *runtime.Scheme) error {
	return RegisterDefaults(scheme)
}

// SetDefaults_<Kind> sets defaults for <Kind>.
func SetDefaults_<Kind>(obj *<Kind>) {
	SetDefaults_<Kind>Spec(&obj.Spec)
}

// SetDefaults_<Kind>Spec sets defaults for <Kind>Spec.
func SetDefaults_<Kind>Spec(obj *<Kind>Spec) {
	if obj.Mode == "" {
		obj.Mode = <Kind>ModeAutomatic
	}
}
```

Use pointers when zero is a valid explicit user choice and absence must remain
distinguishable. Never overwrite a non-zero or non-nil value. `RegisterDefaults`
and `SetObjectDefaults_*` belong to `zz_generated.defaults.go`; never hand-write
them.

## Tests

For every validation rule, cover the valid boundary and each invalid class with
the exact field path. For every default, cover both the unset case and the case
where an explicit user value must be preserved.

For a status-bearing resource, add cases for every phase value class,
condition-key duplication, invalid condition status/severity, generation
bounds, and a valid status update carrying normal update metadata.

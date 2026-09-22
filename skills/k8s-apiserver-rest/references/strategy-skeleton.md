# Strategy skeleton

`internal/apiserver/registry/<group>/<kind>/strategy.go` implements the REST
create/update/delete contract. Reproduce the shape below with `<kind>`
(lowerCamel, e.g. `aiworkload`), `<Kind>` (UpperCamel, e.g. `AIWorkload`),
`<group>` (group package), and `<module>` (module path from `go.mod`).

```go
package <kind>

import (
	"context"
	"fmt"

	apiequality "k8s.io/apimachinery/pkg/api/equality"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/validation/field"
	"k8s.io/apiserver/pkg/registry/generic"
	"k8s.io/apiserver/pkg/registry/rest"
	"k8s.io/apiserver/pkg/storage"
	"k8s.io/apiserver/pkg/storage/names"
	"sigs.k8s.io/structured-merge-diff/v6/fieldpath"

	"<module>/pkg/apis/<group>"
	"<module>/pkg/apis/<group>/validation"
)

// <kind>Strategy implements behavior for <Kind> objects.
type <kind>Strategy struct {
	runtime.ObjectTyper
	names.NameGenerator
}

// Strategy is the default logic that applies when creating and updating <Kind> objects via the REST API.
var Strategy = <kind>Strategy{legacyscheme.Scheme, names.SimpleNameGenerator}

var (
	// Make sure we correctly implement the interface.
	_ rest.RESTCreateStrategy = Strategy
	// Strategy should implement rest.RESTUpdateStrategy.
	_ rest.RESTUpdateStrategy = Strategy
	// Strategy should implement rest.GarbageCollectionDeleteStrategy.
	_ rest.GarbageCollectionDeleteStrategy = Strategy
)

// DefaultGarbageCollectionPolicy returns DeleteDependents for the served resource.
func (<kind>Strategy) DefaultGarbageCollectionPolicy(ctx context.Context) rest.GarbageCollectionPolicy {
	return rest.DeleteDependents
}

// NamespaceScoped reports whether the resource is namespace-scoped.
func (<kind>Strategy) NamespaceScoped() bool {
	return true
}

// GetResetFields returns the set of fields reset by the strategy and not modifiable by the user.
func (<kind>Strategy) GetResetFields() map[fieldpath.APIVersion]*fieldpath.Set {
	return map[fieldpath.APIVersion]*fieldpath.Set{
		"<group>/<version>": fieldpath.NewSet(
			fieldpath.MakePathOrDie("status"),
		),
	}
}

// PrepareForCreate clears fields not allowed to be set by end users on creation.
func (<kind>Strategy) PrepareForCreate(ctx context.Context, obj runtime.Object) {
	k := obj.(*<group>.<Kind>)
	k.Status = <group>.<Kind>Status{}
	k.Generation = 1
	drop<Kind>DisabledFields(k, nil)
}

// Validate validates a new object.
func (<kind>Strategy) Validate(ctx context.Context, obj runtime.Object) field.ErrorList {
	return validation.Validate<Kind>(obj.(*<group>.<Kind>))
}

// WarningsOnCreate returns warnings for the creation of the given object.
func (<kind>Strategy) WarningsOnCreate(ctx context.Context, obj runtime.Object) []string { return nil }

// Canonicalize normalizes the object after validation.
func (<kind>Strategy) Canonicalize(obj runtime.Object) {}

// AllowCreateOnUpdate reports whether create-on-update is permitted (false for this resource).
func (<kind>Strategy) AllowCreateOnUpdate(ctx context.Context) bool { return false }

// PrepareForUpdate clears fields not allowed to be set by end users on update.
func (<kind>Strategy) PrepareForUpdate(ctx context.Context, obj, old runtime.Object) {
	newObj := obj.(*<group>.<Kind>)
	oldObj := old.(*<group>.<Kind>)
	newObj.Status = oldObj.Status

	drop<Kind>DisabledFields(newObj, oldObj)

	if !apiequality.Semantic.DeepEqual(oldObj.Spec, newObj.Spec) {
		newObj.Generation = oldObj.Generation + 1
	}
}

// ValidateUpdate is the default update validation for an end user.
func (<kind>Strategy) ValidateUpdate(ctx context.Context, obj, old runtime.Object) field.ErrorList {
	return validation.Validate<Kind>Update(obj.(*<group>.<Kind>), old.(*<group>.<Kind>))
}

// WarningsOnUpdate returns warnings for the given update.
func (<kind>Strategy) WarningsOnUpdate(ctx context.Context, obj, old runtime.Object) []string {
	return nil
}

// AllowUnconditionalUpdate reports whether a missing resourceVersion skips the concurrency check.
func (<kind>Strategy) AllowUnconditionalUpdate(ctx context.Context) bool { return true }

// <kind>StatusStrategy is the strategy for the /status subresource.
type <kind>StatusStrategy struct {
	<kind>Strategy
}

// StatusStrategy is the default logic invoked when updating object status.
var StatusStrategy = <kind>StatusStrategy{Strategy}

// GetResetFields returns the fields reset by the status strategy.
func (<kind>StatusStrategy) GetResetFields() map[fieldpath.APIVersion]*fieldpath.Set {
	return map[fieldpath.APIVersion]*fieldpath.Set{
		"<group>/<version>": fieldpath.NewSet(
			fieldpath.MakePathOrDie("spec"),
		),
	}
}

// PrepareForUpdate guards fields during a status update.
func (<kind>StatusStrategy) PrepareForUpdate(ctx context.Context, obj, old runtime.Object) {
	newObj := obj.(*<group>.<Kind>)
	oldObj := old.(*<group>.<Kind>)

	newObj.Spec = oldObj.Spec
	newObj.DeletionTimestamp = nil
	newObj.OwnerReferences = oldObj.OwnerReferences
}

// ValidateUpdate validates an update to the status subresource.
func (<kind>StatusStrategy) ValidateUpdate(ctx context.Context, obj, old runtime.Object) field.ErrorList {
	return validation.Validate<Kind>StatusUpdate(obj.(*<group>.<Kind>), old.(*<group>.<Kind>))
}

// WarningsOnUpdate returns warnings for the given status update.
func (<kind>StatusStrategy) WarningsOnUpdate(ctx context.Context, obj, old runtime.Object) []string {
	return nil
}

// Canonicalize normalizes the object after validation.
func (<kind>StatusStrategy) Canonicalize(obj runtime.Object) {}

// ToSelectableFields returns the field set usable for filtering.
func ToSelectableFields(obj *<group>.<Kind>) fields.Set {
	return generic.ObjectMetaFieldsSet(&obj.ObjectMeta, true)
}

// GetAttrs returns labels and fields for filtering.
func GetAttrs(obj runtime.Object) (labels.Set, fields.Set, error) {
	k, ok := obj.(*<group>.<Kind>)
	if !ok {
		return nil, nil, fmt.Errorf("given object is not a <kind>")
	}
	return labels.Set(k.Labels), ToSelectableFields(k), nil
}

// Matcher is the filter used by the generic etcd backend to watch events.
func Matcher(label labels.Selector, field fields.Selector) storage.SelectionPredicate {
	return storage.SelectionPredicate{
		Label:       label,
		Field:       field,
		GetAttrs:    GetAttrs,
		IndexFields: []string{"metadata.name"},
	}
}

// NameTriggerFunc returns the object name for the metadata.name index.
func NameTriggerFunc(obj runtime.Object) string {
	return obj.(*<group>.<Kind>).ObjectMeta.Name
}

// drop<Kind>DisabledFields clears fields that are feature-gated off.
func drop<Kind>DisabledFields(k *<group>.<Kind>, old *<group>.<Kind>) {}
```

## Notes

- `legacyscheme` resolves to the repository's process-wide scheme
  (the apiserver's `legacyscheme.Scheme`). Use the identifier the repository
  already uses; do not import a foreign scheme.
- `NamespaceScoped()` returns `false` for cluster-scoped resources.
- `GetResetFields` lists the write-protected paths per served version; keep
  `status` for the main strategy and `spec` for the status strategy.
- The `drop<Kind>DisabledFields` helper is a no-op when there are no
  feature-gated fields; keep the name and empty body for consistency with the
  surrounding conventions.
- `DefaultGarbageCollectionPolicy` reflects ownership: `rest.DeleteDependents`
  when the resource owns dependents that should cascade on delete;
  `rest.OrphanDependents` when it owns none (deletion must never cascade).
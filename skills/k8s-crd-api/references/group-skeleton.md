# Group skeleton

Boilerplate for a new group, or reference when editing an existing one.

## doc.go — internal (`pkg/apis/<group>/doc.go`)

```go
// +k8s:deepcopy-gen=package
// +groupName=<group>

// Package <group> is the internal version of the API.
package <group>
```

## doc.go — external (`pkg/apis/<group>/<version>/doc.go`)

```go
// +k8s:openapi-gen=true
// +k8s:deepcopy-gen=package
// +k8s:protobuf-gen=package
// +k8s:conversion-gen=<internal import path>
// +k8s:conversion-gen-external-types=<this package import path>
// +k8s:defaulter-gen=TypeMeta
// +groupName=<group>

// Package <version> is the <version> version of the API.
package <version>
```

This external API is protobuf-enabled. For an existing repository, preserve
the marker set and order from a neighboring external package.

## register.go — internal

```go
package <group>

import (
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

var (
	// SchemeBuilder stores functions to add things to a scheme.
	SchemeBuilder = runtime.NewSchemeBuilder(addKnownTypes)
	// AddToScheme applies all stored functions to a scheme.
	AddToScheme = SchemeBuilder.AddToScheme
)

// GroupName is the group name used in this package.
const GroupName = "<group>"

// SchemeGroupVersion is the group version used to register these objects.
var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: runtime.APIVersionInternal}

// Kind takes an unqualified kind and returns a Group-qualified GroupKind.
func Kind(kind string) schema.GroupKind {
	return SchemeGroupVersion.WithKind(kind).GroupKind()
}

// Resource takes an unqualified resource and returns a Group-qualified GroupResource.
func Resource(resource string) schema.GroupResource {
	return SchemeGroupVersion.WithResource(resource).GroupResource()
}

// addKnownTypes adds the list of known types to the given scheme.
func addKnownTypes(scheme *runtime.Scheme) error {
	scheme.AddKnownTypes(SchemeGroupVersion,
		&<Kind>{},
		&<Kind>List{},
	)
	return nil
}
```

## register.go — external

```go
package <version>

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

// GroupName is the group name used in this package.
const GroupName = "<group>"

// SchemeGroupVersion is the group version used to register these objects.
var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: "<version>"}

// Resource takes an unqualified resource and returns a Group-qualified GroupResource.
func Resource(resource string) schema.GroupResource {
	return SchemeGroupVersion.WithResource(resource).GroupResource()
}

var (
	// SchemeBuilder stores functions to add things to a scheme.
	SchemeBuilder      = runtime.NewSchemeBuilder(addKnownTypes, addDefaultingFuncs)
	localSchemeBuilder = &SchemeBuilder
	// AddToScheme applies all stored functions to a scheme.
	AddToScheme        = localSchemeBuilder.AddToScheme
)

// addKnownTypes adds the list of known types to the given scheme.
func addKnownTypes(scheme *runtime.Scheme) error {
	scheme.AddKnownTypes(SchemeGroupVersion,
		&<Kind>{},
		&<Kind>List{},
	)
	metav1.AddToGroupVersion(scheme, SchemeGroupVersion)
	return nil
}
```

When adding a Kind to an existing group, append `&<Kind>{}` and `&<Kind>List{}`
to the existing `addKnownTypes` in both packages. Do not recreate the file.

## install (`pkg/apis/<group>/install/install.go`)

```go
// Package install installs the <group> API group, making it available to the
// encoding/decoding machinery.
package install

import (
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"

	"<module>/pkg/apis/<group>"
	<group><version> "<module>/pkg/apis/<group>/<version>"
)

// Install registers the API group and adds its types to the scheme.
func Install(scheme *runtime.Scheme) {
	utilruntime.Must(<group>.AddToScheme(scheme))
	utilruntime.Must(<group><version>.AddToScheme(scheme))
	utilruntime.Must(scheme.SetVersionPriority(<group><version>.SchemeGroupVersion))
}
```

The `init()` wiring depends on the project's global scheme; adapt to how the
project exposes it (e.g. a legacy scheme or an apiserver scheme), and keep the
`Install(scheme)` function the single entry point.

## OWNERS (`pkg/apis/<group>/OWNERS`)

Do not create or modify the top-level `pkg/apis/OWNERS`; inspect it only to
understand inherited ownership. Create the group-level file below only for a
new group and only when neighboring groups use this convention.

```yaml
reviewers:
  - <reviewer>
labels:
  - <domain>/scheme
  - <domain>/<group-package>
```

The existing top-level file supplies inherited approvers. Group OWNERS normally
refine reviewers and labels without duplicating approvers; preserve the
repository's existing label namespace.

## Conditions (`condition_types.go`)

Conditions are **group-local**: each group defines its own `condition_types.go`
and `condition_consts.go`; do not extract a shared condition package. A
framework-level condition helper, if one exists, operates on this group's types.

Define the same API shape in both packages, using `core.ConditionStatus`
internally and `corev1.ConditionStatus` externally. External fields require
protobuf tags; internal tags follow the neighboring package convention. The
external form is:

```go
// ConditionSeverity expresses the severity of a Condition Type failing.
type ConditionSeverity string

const (
	// ConditionSeverityError specifies that a condition with Status=False is an error.
	ConditionSeverityError ConditionSeverity = "Error"

	// ConditionSeverityWarning specifies that a condition with Status=False is a warning.
	ConditionSeverityWarning ConditionSeverity = "Warning"

	// ConditionSeverityInfo specifies that a condition with Status=False is informative.
	ConditionSeverityInfo ConditionSeverity = "Info"

	// ConditionSeverityNone applies only to conditions with Status=True.
	ConditionSeverityNone ConditionSeverity = ""
)

// ConditionType is a valid value for Condition.Type.
type ConditionType string

// Condition defines an observation of a resource's operational state.
type Condition struct {
	// Type identifies the condition in CamelCase or in example.io/CamelCase form.
	Type ConditionType `json:"type" protobuf:"bytes,1,opt,name=type,casttype=ConditionType"`

	// Status is one of True, False, or Unknown.
	Status corev1.ConditionStatus `json:"status" protobuf:"bytes,2,opt,name=status,casttype=k8s.io/api/core/v1.ConditionStatus"`

	// Severity provides an explicit classification of the Reason code.
	// The Severity field MUST be set only when Status=False.
	// +optional
	Severity ConditionSeverity `json:"severity" protobuf:"bytes,3,opt,name=severity,casttype=ConditionSeverity"`

	// LastTransitionTime records when the condition last changed status.
	LastTransitionTime metav1.Time `json:"lastTransitionTime,omitempty" protobuf:"bytes,4,opt,name=lastTransitionTime"`

	// Reason identifies the condition's last transition in CamelCase.
	// +optional
	Reason string `json:"reason,omitempty" protobuf:"bytes,5,opt,name=reason"`

	// Message provides human-readable details about the transition.
	// +optional
	Message string `json:"message,omitempty" protobuf:"bytes,6,opt,name=message"`
}

// Conditions provide observations of the operational state of a resource.
type Conditions []Condition
```

In the internal copy, replace `corev1.ConditionStatus` with
`core.ConditionStatus`; keep the cast target pointing to
`k8s.io/api/core/v1.ConditionStatus` when protobuf tags are present.

ConditionType / Reason constants go in `condition_consts.go` (external version).
Every exported constant gets its own identifier-first comment. Reason comments
include `(Severity=Error|Warning|Info)` when the reason represents a false
condition. Add documented `GetConditions()` / `SetConditions()` methods on the
external root object — these are required, not optional:

```go
// GetConditions returns the conditions for this object.
func (x *<Kind>) GetConditions() Conditions { return x.Status.Conditions }

// SetConditions sets the conditions for this object.
func (x *<Kind>) SetConditions(c Conditions) { x.Status.Conditions = c }
```

For defaulting and runtime validation, read
[`validation-defaulting.md`](validation-defaulting.md) only in Phase 5.

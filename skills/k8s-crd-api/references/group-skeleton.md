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
// +k8s:conversion-gen=<internal import path>
// +k8s:conversion-gen-external-types=<this package import path>
// +k8s:defaulter-gen=TypeMeta
// +groupName=<group>

// Package <version> is the <version> version of the API.
package <version>
```

Add `+k8s:protobuf-gen=package` only when protobuf bindings are wanted.

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
	SchemeBuilder      = runtime.NewSchemeBuilder(addKnownTypes, addDefaultingFuncs)
	localSchemeBuilder = &SchemeBuilder
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

```yaml
approvers:
  - <maintainer>
reviewers:
  - <reviewer>
labels:
  - <group>
```

Top-level `pkg/apis/OWNERS` holds global approvers; group OWNERS refine
reviewers and labels.

## Conditions (`condition_types.go`)

```go
// ConditionSeverity expresses the severity of a Condition Type failing.
type ConditionSeverity string

const (
	ConditionSeverityError   ConditionSeverity = "Error"
	ConditionSeverityWarning ConditionSeverity = "Warning"
	ConditionSeverityInfo    ConditionSeverity = "Info"
	ConditionSeverityNone    ConditionSeverity = ""
)

// ConditionType is a valid value for Condition.Type.
type ConditionType string

// Condition defines an observation of a resource's operational state.
type Condition struct {
	// Type of condition in CamelCase or in foo.example.com/CamelCase.
	Type ConditionType `json:"type"`

	// Status of the condition, one of True, False, Unknown.
	Status metav1.ConditionStatus `json:"status"`

	// Severity provides an explicit classification of the Reason code.
	// The Severity field MUST be set only when Status=False.
	// +optional
	Severity ConditionSeverity `json:"severity,omitempty"`

	// Last time the condition transitioned from one status to another.
	LastTransitionTime metav1.Time `json:"lastTransitionTime,omitempty"`

	// The reason for the condition's last transition in CamelCase.
	// +optional
	Reason string `json:"reason,omitempty"`

	// A human readable message indicating details about the transition.
	// +optional
	Message string `json:"message,omitempty"`
}

// Conditions provide observations of the operational state of a resource.
type Conditions []Condition
```

ConditionType / Reason constants go in `condition_consts.go` (external version),
each documented with its Severity semantics. Add `GetConditions()` /
`SetConditions()` on the root object:

```go
func (x *<Kind>) GetConditions() Conditions { return x.Status.Conditions }
func (x *<Kind>) SetConditions(c Conditions) { x.Status.Conditions = c }
```

## Defaulting (`defaults.go`, external version — hand-written)

```go
func addDefaultingFuncs(scheme *runtime.Scheme) error {
	return RegisterDefaults(scheme)
}

// SetDefaults_<Kind> sets defaults for <Kind>.
func SetDefaults_<Kind>(obj *<Kind>) {
	SetDefaults_<Kind>Spec(&obj.Spec)
}

// SetDefaults_<Kind>Spec sets defaults for <Kind> spec.
func SetDefaults_<Kind>Spec(obj *<Kind>Spec) {
	if obj.Field == "" {
		obj.Field = "<default>"
	}
}
```

`RegisterDefaults` and `SetObjectDefaults_*` are generated
(`zz_generated.defaults.go`) — never hand-write them.

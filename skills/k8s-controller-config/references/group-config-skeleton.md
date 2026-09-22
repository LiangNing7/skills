# Domain config skeleton

`internal/controller/<group>/apis/config/` carries one business domain's
controller configuration. `<Group>` is the UpperCamel group name, `<domain>`
the project's DNS domain, `<module>` the module path. The tree shape is
identical to the shared config's — the differences are the group name string,
the fields, and the per-controller nested blocks.

## Internal type (`types.go`)

```go
// +k8s:deepcopy-gen=package
// +groupName=<group>controller.config.<domain>

package config // import <module>/internal/controller/<group>/apis/config

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	genericconfig "<module>/pkg/config"
)

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Group>ControllerConfiguration configures the <group> controller-manager.
type <Group>ControllerConfiguration struct {
	metav1.TypeMeta

	// Generic holds configuration for a generic controller-manager.
	Generic genericconfig.GenericControllerManagerConfiguration

	// DryRun tells if the dry run mode is enabled: do not create the actual
	// owned resources, but directly mark the status as ready.
	// If DryRun is set to true, the DryRun mode will be prioritized.
	// +optional
	DryRun bool

	// FeatureGates is a map of feature names to bools that enable or disable alpha/experimental features.
	FeatureGates map[string]bool

	// <Controller>Controller holds configuration for the <controller> controller.
	// +optional
	<Controller>Controller <Controller>ControllerConfiguration
}

// <Controller>ControllerConfiguration contains the <controller> controller's own knobs.
type <Controller>ControllerConfiguration struct {
	// Concurrency is the number of workers for this controller. Must be > 0.
	// +optional
	Concurrency int32
}
```

**When to embed the generic block.** Only when this domain's config file must
carry generic settings — the domain runs as its own component and loads its
own config file. In a single-binary repo (one controller-manager loading one
overall config), omit `Generic` entirely: generic settings come from the
shared config, and the domain tree stays pure domain knobs. The two
directions are mutually exclusive — a domain tree importing the generic block
and the shared config referencing the domain's types together form an import
cycle.

## Versioned type (`v1beta1/types.go`)

Mirrors the internal type with json tags; use pointers for fields whose
"unset vs false/0" must survive defaulting:

```go
package v1beta1

// +k8s:deepcopy-gen=package
// +groupName=<group>controller.config.<domain>

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Group>ControllerConfiguration configures the <group> controller-manager.
type <Group>ControllerConfiguration struct {
	metav1.TypeMeta `json:",inline"`

	// Generic holds configuration for a generic controller-manager.
	Generic genericconfigv1beta1.GenericControllerManagerConfiguration `json:"generic,omitempty"`

	// DryRun tells if the dry run mode is enabled.
	// +optional
	DryRun *bool `json:"dryRun,omitempty"`

	// <Controller>Controller holds configuration for the <controller> controller.
	// +optional
	<Controller>Controller <Controller>ControllerConfiguration `json:"<controller>Controller,omitempty"`
}

// <Controller>ControllerConfiguration contains the <controller> controller's own knobs.
type <Controller>ControllerConfiguration struct {
	// Concurrency is the number of workers for this controller. Must be > 0.
	// +optional
	Concurrency *int32 `json:"concurrency,omitempty"`
}
```

## Register (`register.go`, `v1beta1/register.go`)

Internal — group name is `<group>controller.config.<domain>`, version is
`runtime.APIVersionInternal`:

```go
package config

var (
	// SchemeBuilder is the scheme builder with scheme init functions to run for this API package.
	SchemeBuilder = runtime.NewSchemeBuilder(addKnownTypes)
	// AddToScheme is a global function that registers this API group & version to a scheme.
	AddToScheme = SchemeBuilder.AddToScheme
)

// GroupName is the group name used in this package.
const GroupName = "<group>controller.config.<domain>"

// SchemeGroupVersion is group version used to register these objects.
var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: runtime.APIVersionInternal}

// addKnownTypes registers known types to the given scheme.
func addKnownTypes(scheme *runtime.Scheme) error {
	scheme.AddKnownTypes(SchemeGroupVersion,
		&<Group>ControllerConfiguration{},
	)
	return nil
}
```

External — same group name, version `"v1beta1"`, defaulting registered via
`localSchemeBuilder`:

```go
package v1beta1

// GroupName is the group name used in this package.
const GroupName = "<group>controller.config.<domain>"

// SchemeGroupVersion is group version used to register these objects.
var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: "v1beta1"}

var (
	SchemeBuilder      = runtime.NewSchemeBuilder(addKnownTypes)
	localSchemeBuilder = &SchemeBuilder
	// AddToScheme is a global function that registers this API group & version to a scheme.
	AddToScheme = localSchemeBuilder.AddToScheme
)

func init() {
	// We only register manually written functions here. The registration of the
	// generated functions takes place in the generated files. The separation
	// makes the code compile even when the generated files are missing.
	localSchemeBuilder.Register(addDefaultingFuncs)
}
```

## Scheme (`scheme/scheme.go`)

Same shape as the shared config's scheme package:

```go
package scheme

var (
	// Scheme defines methods for serializing and deserializing API objects.
	Scheme = legacyscheme.Scheme
	// Codecs provides methods for retrieving codecs and serializers for specific
	// versions and content types.
	Codecs = serializer.NewCodecFactory(legacyscheme.Scheme, serializer.EnableStrict)
)

func init() {
	AddToScheme(legacyscheme.Scheme)
}

// AddToScheme registers the API group and adds types to a scheme.
func AddToScheme(scheme *runtime.Scheme) {
	utilruntime.Must(config.AddToScheme(scheme))
	utilruntime.Must(v1beta1.AddToScheme(scheme))
	utilruntime.Must(scheme.SetVersionPriority(v1beta1.SchemeGroupVersion))
}
```

## Defaulting (`v1beta1/defaults.go`)

```go
package v1beta1

func addDefaultingFuncs(scheme *runtime.Scheme) error {
	return RegisterDefaults(scheme)
}

// SetDefaults_<Group>ControllerConfiguration sets defaults for the <group> config.
func SetDefaults_<Group>ControllerConfiguration(obj *<Group>ControllerConfiguration) {
	genericconfigv1beta1.RecommendedDefaultGenericControllerManagerConfiguration(&obj.Generic)
	RecommendedDefault<Controller>ControllerConfiguration(&obj.<Controller>Controller)
}

// RecommendedDefault<Controller>ControllerConfiguration sets recommended defaults for the <controller> controller.
func RecommendedDefault<Controller>ControllerConfiguration(obj *<Controller>ControllerConfiguration) {
	if obj.Concurrency == nil {
		obj.Concurrency = ptr.To(Default<Controller>Concurrency)
	}
}
```

## Latest (`latest/latest.go`)

```go
package latest

// Default creates a default configuration of the latest versioned type.
// This function needs to be updated whenever we bump the <group> controller's
// component config version.
func Default() (*config.<Group>ControllerConfiguration, error) {
	versionedCfg := v1beta1.<Group>ControllerConfiguration{}

	scheme.Scheme.Default(&versionedCfg)
	cfg := config.<Group>ControllerConfiguration{}
	if err := scheme.Scheme.Convert(&versionedCfg, &cfg, nil); err != nil {
		return nil, err
	}
	cfg.TypeMeta.APIVersion = v1beta1.SchemeGroupVersion.String()
	return &cfg, nil
}
```

## Validation (`validation/validation.go`)

```go
package validation

// Validate validates a <Group>ControllerConfiguration.
func Validate(cfg *config.<Group>ControllerConfiguration) field.ErrorList {
	allErrs := field.ErrorList{}
	allErrs = append(allErrs, Validate<Controller>ControllerConfiguration(&cfg.<Controller>Controller, field.NewPath("<controller>Controller"))...)
	return allErrs
}

// Validate<Controller>ControllerConfiguration validates the <controller> controller config.
func Validate<Controller>ControllerConfiguration(cfg *config.<Controller>ControllerConfiguration, fldPath *field.Path) field.ErrorList {
	allErrs := field.ErrorList{}
	if cfg.Concurrency < 0 {
		allErrs = append(allErrs, field.Invalid(fldPath.Child("concurrency"), cfg.Concurrency, "must be >= 0"))
	}
	return allErrs
}
```

## Codegen

- Tags in `doc.go` (`+k8s:deepcopy-gen=package`, `+groupName=...`) drive the
  repo's codegen script; run it after writing the tree so
  `zz_generated.deepcopy.go`, `zz_generated.defaults.go`, and
  `zz_generated.conversion.go` are produced for both the internal and the
  versioned package.
- The `init()`/`localSchemeBuilder` separation in `v1beta1/register.go` exists
  precisely so the package compiles with the generated files missing — write
  hand-written files first, then codegen, in that order.

## Consumption

- The controller-manager entry loads the domain config the same way as the
  shared one: versioned → `latest.Default()` (or `scheme.Scheme.Default`) →
  convert to internal → `Validate`.
- Each reconciler receives only its nested block, e.g.
  `ComponentConfig: &cfg.<Controller>Controller`. Worker count and sync period
  come from `Generic.Parallelism` / `Generic.SyncPeriod` (or the controller's
  own `Concurrency`) into the shared controller options.
- After this tree exists, add the domain's top-level block to the shared config
  (`internal/controller/apis/config/types.go` + `v1beta1/types.go` +
  `v1beta1/defaults.go`) so the overall config file can carry it — as a local
  mirror type, never an import of this tree's types (see `file-map.md`).
- Building the reconciler that consumes `ComponentConfig` is out of scope
  (k8s-controller).

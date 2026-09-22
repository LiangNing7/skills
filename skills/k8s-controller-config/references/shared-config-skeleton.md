# Shared (overall) config skeleton

`internal/controller/apis/config/` carries the controller-manager binary's
overall configuration. `<Module>` is the UpperCamel project/module name,
`<domain>` the project's DNS domain, `<module>` the module path.

## Internal type (`types.go`)

```go
// +k8s:deepcopy-gen:package
// +groupName=controllermanager.config.<domain>

package config // import <module>/internal/controller/apis/config

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	genericconfig "<module>/pkg/config"
)

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Module>ControllerManagerConfiguration contains elements describing the
// <module> controller-manager.
type <Module>ControllerManagerConfiguration struct {
	metav1.TypeMeta

	// Generic holds configuration shared across controller-managers.
	Generic genericconfig.GenericControllerManagerConfiguration

	// MySQL defines the configuration of the mysql client.
	MySQL genericconfig.MySQLConfiguration

	// <Group>Controller holds configuration for <group> related features.
	<Group>Controller <Group>ControllerConfiguration
}

// <Group>ControllerConfiguration holds configuration for the <group> domain's controllers.
type <Group>ControllerConfiguration struct {
	// Image specify the <group> workload image.
	Image string
}
```

The generic block and infra client blocks come from `pkg/config` — embed, do
not re-declare. Each business domain contributes one top-level block; the block
type may live here (small) or reference the domain's own config types.

## Versioned type (`v1beta1/types.go`)

Mirrors the internal type with json tags and pointer-ized optional scalars:

```go
package v1beta1

// +k8s:deepcopy-gen=package
// +groupName=controllermanager.config.<domain>

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Module>ControllerManagerConfiguration contains elements describing the
// <module> controller-manager.
type <Module>ControllerManagerConfiguration struct {
	metav1.TypeMeta `json:",inline"`

	// Generic holds configuration for a generic controller-manager.
	Generic genericconfigv1beta1.GenericControllerManagerConfiguration `json:"generic,omitempty"`

	// MySQL defines the configuration of mysql client.
	MySQL genericconfigv1beta1.MySQLConfiguration `json:"mysql,omitempty"`

	// <Group>Controller holds configuration for <group> related features.
	<Group>Controller <Group>ControllerConfiguration `json:"<group>Controller,omitempty"`
}

// <Group>ControllerConfiguration holds configuration for the <group> domain's controllers.
type <Group>ControllerConfiguration struct {
	// Image specify the <group> workload image.
	// +optional
	Image *string `json:"image,omitempty"`
}
```

## Register (`register.go`, `v1beta1/register.go`)

Internal — version is `runtime.APIVersionInternal`:

```go
package config

var (
	// SchemeBuilder is the scheme builder with scheme init functions to run for this API package.
	SchemeBuilder = runtime.NewSchemeBuilder(addKnownTypes)
	// AddToScheme is a global function that registers this API group & version to a scheme.
	AddToScheme = SchemeBuilder.AddToScheme
)

// GroupName is the group name used in this package.
const GroupName = "controllermanager.config.<domain>"

// SchemeGroupVersion is group version used to register these objects.
var SchemeGroupVersion = schema.GroupVersion{Group: GroupName, Version: runtime.APIVersionInternal}

// addKnownTypes registers known types to the given scheme.
func addKnownTypes(scheme *runtime.Scheme) error {
	scheme.AddKnownTypes(SchemeGroupVersion,
		&<Module>ControllerManagerConfiguration{},
	)
	return nil
}
```

External — version is `"v1beta1"`, and defaulting funcs are registered through
`localSchemeBuilder`:

```go
package v1beta1

// GroupName is the group name used in this package.
const GroupName = "controllermanager.config.<domain>"

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

// SetDefaults_<Module>ControllerManagerConfiguration sets defaults for the overall config.
func SetDefaults_<Module>ControllerManagerConfiguration(obj *<Module>ControllerManagerConfiguration) {
	genericconfigv1beta1.RecommendedDefaultGenericControllerManagerConfiguration(&obj.Generic)
	genericconfigv1beta1.RecommendedDefaultMySQLConfiguration(&obj.MySQL)
	RecommendedDefault<Group>ControllerConfiguration(&obj.<Group>Controller)
}

// RecommendedDefault<Group>ControllerConfiguration sets recommended defaults for the <group> block.
func RecommendedDefault<Group>ControllerConfiguration(obj *<Group>ControllerConfiguration) {
	if obj.Image == nil {
		obj.Image = ptr.To(Default<Group>Image)
	}
}
```

## Latest (`latest/latest.go`)

```go
package latest

// Default creates a default configuration of the latest versioned type.
// This function needs to be updated whenever we bump the controller-manager's
// component config version.
func Default() (*config.<Module>ControllerManagerConfiguration, error) {
	versionedCfg := v1beta1.<Module>ControllerManagerConfiguration{}

	scheme.Scheme.Default(&versionedCfg)
	cfg := config.<Module>ControllerManagerConfiguration{}
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

// Validate validates a <Module>ControllerManagerConfiguration.
func Validate(cfg *config.<Module>ControllerManagerConfiguration) field.ErrorList {
	allErrs := field.ErrorList{}
	allErrs = append(allErrs, Validate<Group>ControllerConfiguration(&cfg.<Group>Controller, field.NewPath("<group>Controller"))...)
	return allErrs
}

// Validate<Group>ControllerConfiguration validates the <group> block of the config.
func Validate<Group>ControllerConfiguration(cfg *config.<Group>ControllerConfiguration, fldPath *field.Path) field.ErrorList {
	allErrs := field.ErrorList{}
	if cfg.Image == "" {
		allErrs = append(allErrs, field.Required(fldPath.Child("image"), "must specify an image"))
	}
	return allErrs
}
```

## Codegen & consumption

- Tags in `doc.go` (`+k8s:deepcopy-gen=package`, `+groupName=...`) drive the
  repo's codegen script (deepcopy-gen / defaulter-gen / conversion-gen);
  re-run it after every type change so `zz_generated.*` files track the types.
- The controller-manager entry consumes the config: flags and/or
  `--<module>-config` file → decode into the versioned type →
  `latest.Default()` (or `scheme.Scheme.Default` on the decoded versioned
  object) → convert to internal → `Validate` → completed config. Reconcilers
  receive only their own nested block via `ComponentConfig`; worker count and
  sync period are read from `Generic.Parallelism` / `Generic.SyncPeriod` (or
  the controller's own `Concurrency`) into the shared controller options.

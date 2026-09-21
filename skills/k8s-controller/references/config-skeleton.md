# Component config skeleton

`internal/controller/<group>/apis/config/` carries the controller-manager
binary's configuration as versioned types, following the internal + external
version + defaulting + validation convention. `<Group>` is the UpperCamel group
name, `<module>` the module path.

## Internal type (`types.go`)

```go
package config

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/component-base/config"

	genericconfig "<module>/pkg/config"
)

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Group>ControllerConfiguration configures the <group> controller manager.
type <Group>ControllerConfiguration struct {
	metav1.TypeMeta

	// Generic holds configuration shared across controller-managers.
	Generic genericconfig.GenericControllerManagerConfiguration

	// FeatureGates is a map of feature names to bools enabling alpha/experimental features.
	FeatureGates map[string]bool

	// <Controller>Controller holds configuration for the <controller> controller.
	// +optional
	<Controller>Controller <Controller>ControllerConfiguration `json:"<controller>Controller,omitempty"`
}

// <Controller>ControllerConfiguration contains the <controller> controller's own knobs.
type <Controller>ControllerConfiguration struct {
	// Concurrency is the number of workers for this controller. Must be > 0.
	// +optional
	Concurrency int32 `json:"concurrency,omitempty"`
}
```

## Versioned type (`v1beta1/types.go`)

Mirrors the internal type with `json`/`protobuf` tags; use pointers for fields
whose "unset vs false/0" must survive defaulting. The `<Kind>`-level fields live
here as the wire form.

## Defaulting (`v1beta1/defaults.go`)

```go
package v1beta1

// SetDefaults_<Group>ControllerConfiguration sets defaults for the config.
func SetDefaults_<Group>ControllerConfiguration(obj *<Group>ControllerConfiguration) {
	if obj.<Controller>Controller.Concurrency == 0 {
		obj.<Controller>Controller.Concurrency = Default<Controller>Concurrency
	}
}

// RecommendedDefault<Group>ControllerConfiguration returns a config with recommended defaults applied.
func RecommendedDefault<Group>ControllerConfiguration(controllermanager *GenericControllerManagerConfiguration) *<Group>ControllerConfiguration {
	cfg := &<Group>ControllerConfiguration{
		FeatureGates: map[string]bool{},
	}
	// ... assign recommended values ...
	return cfg
}
```

Register defaulting by appending `SetDefaults_<Group>ControllerConfiguration` in
`addDefaultingFuncs` inside `register.go`, so `scheme.Default(...)` applies it.

## Scheme + latest

`scheme/scheme.go` builds a `runtime.Scheme` wired with the internal + external
`AddToScheme` (for `Default()`/`Convert()`). `latest/latest.go`:

```go
package latest

import (
	"<module>/internal/controller/<group>/apis/config"
	"<module>/internal/controller/<group>/apis/config/scheme"
	"<module>/internal/controller/<group>/apis/config/v1beta1"
)

// Default returns a default internal config with all defaults applied.
func Default() (*config.<Group>ControllerConfiguration, error) {
	versioned := v1beta1.<Group>ControllerConfiguration{}
	scheme.Scheme.Default(&versioned)
	cfg := config.<Group>ControllerConfiguration{}
	if err := scheme.Scheme.Convert(&versioned, &cfg, nil); err != nil {
		return nil, err
	}
	cfg.TypeMeta.APIVersion = v1beta1.SchemeGroupVersion.String()
	return &cfg, nil
}
```

## Validation (`validation/validation.go`)

```go
package validation

import (
	"k8s.io/apimachinery/pkg/util/validation/field"

	"<module>/internal/controller/<group>/apis/config"
)

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

## Consuming the config

The resolved config reaches reconcilers through the manager's completed config;
registration passes the domain block into the reconciler struct literal, e.g.
`ComponentConfig: &cctx.Config.ComponentConfig.<Controller>Controller`. Worker
count and sync period are read from `Generic.Parallelism` /
`Generic.SyncPeriod` (or the controller's own `Concurrency`) into the shared
controller options.
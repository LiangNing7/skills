# Field-level templates (byte-level)

Exact comment, tag, and marker conventions. Generate code that reads like these
templates. Replace placeholders only.

## Placeholders

| Placeholder | Meaning | Example |
|---|---|---|
| `<Kind>` | UpperCamelCase kind | `Chain` |
| `<kind>` | lowercase singular | `chain` |
| `<plural>` | lowercase plural (resource name) | `chains` |
| `<group>` | DNS-subdomain group | `apps.example.io` |
| `<domain>` | project API domain without the group prefix | `example.io` |

## Top-level object (`<kind>_types.go`)

Use this marker block on the external root object:

```go
// +genclient
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
```

Add `// +genclient:nonNamespaced` between those lines for a cluster-scoped
resource. Use only the deepcopy marker internally. After the applicable marker
block and one blank line, write the object. This example shows the required
external protobuf tags; internal tags follow the neighboring group:

```go

// <Kind> is the Schema for the <plural> API.
type <Kind> struct {
	metav1.TypeMeta `json:",inline"`
	// Standard object's metadata.
	// More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#metadata
	// +optional
	metav1.ObjectMeta `json:"metadata,omitempty" protobuf:"bytes,1,opt,name=metadata"`

	// Specification of the desired behavior of the <kind>.
	// More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#spec-and-status
	// +optional
	Spec <Kind>Spec `json:"spec,omitempty" protobuf:"bytes,2,opt,name=spec"`

	// Status is the most recently observed status of the <Kind>.
	// This data may be out of date by some window of time.
	// Populated by the system.
	// Read-only.
	// More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#spec-and-status
	// +optional
	Status <Kind>Status `json:"status,omitempty" protobuf:"bytes,3,opt,name=status"`
}
```

Rules:

- `TypeMeta` has **no** comment and **no** protobuf tag, only `json:",inline"`.
- Omit `+genclient` in the internal package. Preserve external protobuf tags;
  internal protobuf tags follow the existing group convention.
- The status comment should convey "most recently observed status", that the
  data may be out of date, "Populated by the system.", and "Read-only."; the
  exact wording varies between groups, so match the neighboring files.
- The two `More info:` links are fixed; do not rewrite them.

## List object (same file)

```go
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// <Kind>List is a list of <Kind> objects.
type <Kind>List struct {
	metav1.TypeMeta `json:",inline"`
	// Standard list metadata.
	// More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#metadata
	// +optional
	metav1.ListMeta `json:"metadata,omitempty" protobuf:"bytes,1,opt,name=metadata"`

	// Items is a list of schema objects.
	Items []<Kind> `json:"items" protobuf:"bytes,2,rep,name=items"`
}
```

Rules: use `metav1.ListMeta`; the phrase is "Standard **list** metadata.".
`Items` has no `+optional`, no `omitempty`, and protobuf uses `rep` (repeated).

## Spec struct

```go
// <Kind>Spec defines the desired state of <Kind>.
type <Kind>Spec struct {
	// <Field description, first word is the field name; cover semantics,
	// allowed values, and default.>
	// <optional extra lines: enum values / constraints / default behavior>
	// +optional
	DisplayName string `json:"displayName,omitempty" protobuf:"bytes,1,opt,name=displayName"`

	// Mode is one of Run, Test. Defaults to Run.
	// +kubebuilder:validation:Enum=Run;Test
	// +optional
	Mode string `json:"mode,omitempty" protobuf:"bytes,2,opt,name=mode"`
}
```

Rules: every field comment starts with the field name; pointer + `omitempty`
distinguishes "unset" from "zero"; `// +optional` sits on the last comment line,
directly above the tag.

## Status struct

```go
// <Kind>Status defines the observed state of <Kind>.
type <Kind>Status struct {
	// ObservedGeneration is the latest generation observed by the controller.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty" protobuf:"varint,1,opt,name=observedGeneration"`

	// Conditions defines the current state of the <Kind>.
	// +optional
	Conditions Conditions `json:"conditions,omitempty" protobuf:"bytes,2,rep,name=conditions"`
}
```

## Finalizer constant (top of `<kind>_types.go`)

```go
const (
	// <Kind>Finalizer is the finalizer used by the <Kind> controller to
	// clean up referenced template resources if necessary when a <Kind> is being deleted.
	<Kind>Finalizer = "<kind>.<domain>/finalizer"
)
```

Derive `<domain>` from neighboring finalizers. Do not blindly append the full
API group: for group `apps.example.io`, the established value may be
`chain.example.io/finalizer`, not `chain.apps.example.io/finalizer`.

## Phase enum (`<kind>_phase_types.go`)

```go
// <Kind>Phase is a string representation of a <Kind> Phase.
//
// It is a high-level indicator of the <kind>'s state from the API user's
// perspective. Controllers must not rely on it for decisions; they must
// inspect the actual state fields instead.
// +enum
type <Kind>Phase string

const (
	// <Kind>PhasePending indicates that <describe what is pending and what ends this phase>.
	<Kind>PhasePending = <Kind>Phase("Pending")

	// <Kind>PhaseRunning indicates that <describe the observable running state>.
	<Kind>PhaseRunning = <Kind>Phase("Running")

	// <Kind>PhaseFailed indicates that <describe terminality and required intervention>.
	<Kind>PhaseFailed  = <Kind>Phase("Failed")

	// <Kind>PhaseUnknown indicates that the current state cannot be determined.
	<Kind>PhaseUnknown = <Kind>Phase("Unknown")
)
```

Every Phase value gets its own non-tautological comment beginning with the
constant name. Describe the state, whether it is terminal, and the transition
out when that information is known. Include only values confirmed during the
interview; the four values above demonstrate formatting, not a mandatory set.

## Phase accessors

When `Status` carries the phase as a raw `Phase string` field, add typed
accessors so callers convert through the enum instead of comparing raw strings.
List every non-`Unknown` value in the switch; unrecognized values fall back to
`Unknown`.

```go
// SetTypedPhase sets the Phase field to the string representation of <Kind>Phase.
func (s *<Kind>Status) SetTypedPhase(p <Kind>Phase) {
	s.Phase = string(p)
}

// GetTypedPhase attempts to parse the Phase field and return
// the typed <Kind>Phase representation as described in `<kind>_phase_types.go`.
func (s *<Kind>Status) GetTypedPhase() <Kind>Phase {
	switch phase := <Kind>Phase(s.Phase); phase {
	case
		<Kind>PhasePending,
		<Kind>PhaseRunning,
		<Kind>PhaseFailed:
		return phase
	default:
		return <Kind>PhaseUnknown
	}
}
```

## Typed string enums

Put `// +enum` immediately above the type declaration, not above the `const`
block. Document every exported value separately:

```go
// <Kind>Mode identifies how <Kind> executes.
// +enum
type <Kind>Mode string

const (
	// <Kind>ModeAutomatic lets the system choose the execution strategy.
	<Kind>ModeAutomatic <Kind>Mode = "Automatic"

	// <Kind>ModeManual requires the user to choose the execution strategy.
	<Kind>ModeManual <Kind>Mode = "Manual"
)
```

## Marker → OpenAPI and codegen mapping

| Source marker / comment | Generated effect |
|---|---|
| field doc comment (`// ...`) | OpenAPI `description` |
| `// +optional` | field excluded from `required` |
| (no `+optional`, no `omitempty`) | field included in `required` |
| `// +kubebuilder:validation:Enum=a;b;c` | `enum: [a, b, c]` |
| `// +kubebuilder:validation:XPreserveUnknownFields` | `x-kubernetes-preserve-unknown-fields: true` |
| `// +kubebuilder:validation:MinLength/MaxLength/Pattern/Format` | `minLength` / `maxLength` / `pattern` / `format` |
| `// +patchStrategy=merge` + `// +patchMergeKey=type` | strategic-merge-patch metadata |
| `// +listType=map/atomic/set` | `x-kubernetes-list-type` |
| `// +enum` | OpenAPI enum for a typed string |
| `// +genclient` | client generation (not OpenAPI) |
| `json:"<name>,omitempty"` | JSON/OpenAPI field name + optionality |

## Hard rules

1. Every exported package-level type, constant, variable, function, and method
   has a doc comment beginning with its exact identifier. A shared heading above
   a `const` block does not replace per-constant comments.
2. Every named API struct field has a semantic doc comment. Prefer starting it
   with the field name; preserve the fixed Kubernetes metadata/spec/status
   phrases below where required. Anonymous `TypeMeta` is the only ordinary
   no-comment field in these templates.
3. `json` tag: camelCase; `omitempty` for optional fields; `json:",inline"` for
   embedded metadata.
4. `protobuf` tag (external version required; internal follows the group): sequence
   numbers unique, stable, increasing from 1 within a struct; `opt` = optional,
   `rep` = repeated; `name=` matches the json name; `casttype=` for type aliases;
   use `varint` for integer/bool scalars and `bytes` for strings/messages.
5. Fixed phrases — do not rewrite:
   - `Standard object's metadata.`
   - `Standard list metadata.`
   - `Specification of the desired behavior of the <kind>.`
   - `Populated by the system.` / `Read-only.`
   The Status opening line and the Items line follow common patterns but vary
   between groups — e.g. `Status is the most recently observed status of the
   <Kind>.` vs `Most recently observed status of the <kind>.`, and
   `Items is a list of schema objects.` vs `items is the list of <Kind>s.`.
   Match the neighboring files.
6. Fixed links — do not rewrite:
   - `...#metadata`
   - `...#spec-and-status`
7. Blank line between the final root marker and the `// <Kind> is ...`
   doc comment; `// +optional` abuts the tag.
8. Keep a blank line between independently documented enum constants; this
   keeps each doc comment attached to the intended declaration.
9. `gofmt` aligns embedded-field tags (`metav1.TypeMeta`); never hand-align.

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

## Top-level object (`<kind>_types.go`)

```go
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

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
	Status <Kind>Status `json:"status,omitempty"`
}
```

Rules:

- `TypeMeta` has **no** comment and **no** protobuf tag, only `json:",inline"`.
- The four fixed status phrases ("This data may be out of date… /
  Populated by the system. / Read-only.") are mandatory.
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
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// Conditions defines the current state of the <Kind>.
	// +optional
	Conditions Conditions `json:"conditions,omitempty"`
}
```

## Finalizer constant (top of `<kind>_types.go`)

```go
const (
	// <Kind>Finalizer is the finalizer used by the <Kind> controller to
	// clean up referenced template resources if necessary when a <Kind> is being deleted.
	<Kind>Finalizer = "<kind>.<group>/finalizer"
)
```

## Phase enum (`<kind>_phase_types.go`)

```go
// <Kind>Phase is a string representation of a <Kind> Phase.
//
// It is a high-level indicator of the <kind>'s state from the API user's
// perspective. Controllers must not rely on it for decisions; they must
// inspect the actual state fields instead.
type <Kind>Phase string

// +enum
const (
	<Kind>PhasePending = <Kind>Phase("Pending")
	<Kind>PhaseRunning = <Kind>Phase("Running")
	<Kind>PhaseFailed  = <Kind>Phase("Failed")
	<Kind>PhaseUnknown = <Kind>Phase("Unknown")
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

1. Every field has a doc comment; the first word is the field name (golint).
2. `json` tag: camelCase; `omitempty` for optional fields; `json:",inline"` for
   embedded metadata.
3. `protobuf` tag (external version required; internal optional): sequence
   numbers unique, stable, increasing from 1 within a struct; `opt` = optional,
   `rep` = repeated; `name=` matches the json name; `casttype=` for type aliases.
4. Fixed phrases — do not rewrite:
   - `Standard object's metadata.`
   - `Standard list metadata.`
   - `Specification of the desired behavior of the <kind>.`
   - `Status is the most recently observed status of the <Kind>.`
   - `Populated by the system.` / `Read-only.`
   - `Items is a list of schema objects.`
5. Fixed links — do not rewrite:
   - `...#metadata`
   - `...#spec-and-status`
6. Blank line between the `+k8s:deepcopy-gen` marker and the `// <Kind> is ...`
   doc comment; `// +optional` abuts the tag.
7. `gofmt` aligns embedded-field tags (`metav1.TypeMeta`); never hand-align.

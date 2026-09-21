# Storage & provider skeleton

Two files bind the strategy to an etcd-backed store and expose the group to the
apiserver.

## `internal/apiserver/registry/<group>/<kind>/storage/storage.go`

```go
package storage

import (
	"context"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apiserver/pkg/registry/generic"
	genericregistry "k8s.io/apiserver/pkg/registry/generic/registry"
	"k8s.io/apiserver/pkg/registry/rest"
	"k8s.io/apiserver/pkg/storage"
	"k8s.io/kubernetes/pkg/printers"
	printerstorage "k8s.io/kubernetes/pkg/printers/storage"
	"sigs.k8s.io/structured-merge-diff/v6/fieldpath"

	"<module>/internal/apiserver/registry/<group>/<kind>"
	printersinternal "<module>/internal/pkg/printers/internalversion"
	"<module>/pkg/apis/<group>"
)

// <Kind>Storage includes storage for <kind>s and all subresources.
type <Kind>Storage struct {
	<Kind>  *REST
	Status *StatusREST
}

// NewStorage returns a new instance of <Kind>Storage.
func NewStorage(optsGetter generic.RESTOptionsGetter) (<Kind>Storage, error) {
	<kind>Rest, <kind>StatusRest, err := NewREST(optsGetter)
	if err != nil {
		return <Kind>Storage{}, err
	}

	return <Kind>Storage{
		<Kind>:  <kind>Rest,
		Status: <kind>StatusRest,
	}, nil
}

// REST implements a RESTStorage for <kind>s.
type REST struct {
	*genericregistry.Store
}

// NewREST returns a RESTStorage object that will work against <kind>s.
func NewREST(optsGetter generic.RESTOptionsGetter) (*REST, *StatusREST, error) {
	store := &genericregistry.Store{
		NewFunc:     func() runtime.Object { return &<group>.<Kind>{} },
		NewListFunc: func() runtime.Object { return &<group>.<Kind>List{} },
		PredicateFunc: <kind>.Matcher,
		ObjectNameFunc: func(obj runtime.Object) (string, error) {
			return obj.(*<group>.<Kind>).Name, nil
		},
		DefaultQualifiedResource:  <group>.Resource("<resource>"),
		SingularQualifiedResource: <group>.Resource("<resource>"),

		CreateStrategy:      <kind>.Strategy,
		UpdateStrategy:      <kind>.Strategy,
		DeleteStrategy:      <kind>.Strategy,
		ResetFieldsStrategy: <kind>.Strategy,

		TableConvertor: printerstorage.TableConvertor{TableGenerator: printers.NewTableGenerator().With(printersinternal.AddHandlers)},
	}
	options := &generic.StoreOptions{
		RESTOptions: optsGetter,
		AttrFunc:    <kind>.GetAttrs,
		TriggerFunc: map[string]storage.IndexerFunc{"metadata.name": <kind>.NameTriggerFunc},
	}
	if err := store.CompleteWithOptions(options); err != nil {
		return nil, nil, err
	}

	statusStore := *store
	statusStore.UpdateStrategy = <kind>.StatusStrategy
	statusStore.ResetFieldsStrategy = <kind>.StatusStrategy

	return &REST{store}, &StatusREST{store: &statusStore}, nil
}

// Implement ShortNamesProvider.
var _ rest.ShortNamesProvider = &REST{}

// ShortNames returns the short names for the resource.
func (r *REST) ShortNames() []string {
	return []string{""}
}

var _ rest.CategoriesProvider = &REST{}

// Categories returns the categories the resource is part of.
func (r *REST) Categories() []string {
	return []string{"all"}
}

// StatusREST implements the REST endpoint for changing the status of a <kind>.
type StatusREST struct {
	store *genericregistry.Store
}

// New returns an empty <Kind> object.
func (r *StatusREST) New() runtime.Object {
	return &<group>.<Kind>{}
}

// Destroy cleans up resources on shutdown.
func (r *StatusREST) Destroy() {}

// Get retrieves the object from storage (required to support Patch).
func (r *StatusREST) Get(ctx context.Context, name string, options *metav1.GetOptions) (runtime.Object, error) {
	return r.store.Get(ctx, name, options)
}

// Update alters the status subset of an object.
func (r *StatusREST) Update(
	ctx context.Context,
	name string,
	objInfo rest.UpdatedObjectInfo,
	createValidation rest.ValidateObjectFunc,
	updateValidation rest.ValidateObjectUpdateFunc,
	forceAllowCreate bool,
	options *metav1.UpdateOptions,
) (runtime.Object, bool, error) {
	return r.store.Update(ctx, name, objInfo, createValidation, updateValidation, false, options)
}

// GetResetFields implements rest.ResetFieldsStrategy.
func (r *StatusREST) GetResetFields() map[fieldpath.APIVersion]*fieldpath.Set {
	return r.store.GetResetFields()
}

// ConvertToTable delegates table conversion to the underlying store.
func (r *StatusREST) ConvertToTable(ctx context.Context, object runtime.Object, tableOptions runtime.Object) (*metav1.Table, error) {
	return r.store.ConvertToTable(ctx, object, tableOptions)
}
```

Notes:

- `SingularQualifiedResource` uses the singular (`<resource>`) while
  `DefaultQualifiedResource` uses the plural; pass the plural when the two
  differ from a plain `s` suffix.
- `TableConvertor` and the `printersinternal` import are optional; omit both when
  table output is not requested, and drop the `ShortNames`/`Categories`
  methods when neither applies.
- The `StatusREST` shares the underlying store with `REST`; its `Destroy` is a
  no-op for that reason.

## `internal/apiserver/registry/<group>/rest/storage_<group>.go`

```go
package rest

import (
	"k8s.io/apiserver/pkg/registry/generic"
	"k8s.io/apiserver/pkg/registry/rest"
	genericapiserver "k8s.io/apiserver/pkg/server"
	serverstorage "k8s.io/apiserver/pkg/server/storage"
	"k8s.io/kubernetes/pkg/api/legacyscheme"

	<kind>store "<module>/internal/apiserver/registry/<group>/<kind>/storage"
	serializerutil "<module>/internal/pkg/util/serializer"
	"<module>/pkg/apis/<group>"
	<group><version> "<module>/pkg/apis/<group>/<version>"
	"<module>/pkg/apiserver/storage"
)

// RESTStorageProvider is a struct for <group> REST storage.
type RESTStorageProvider struct{}

// Ensure RESTStorageProvider implements storage.RESTStorageProvider.
var _ storage.RESTStorageProvider = &RESTStorageProvider{}

// NewRESTStorage returns the APIGroupInfo for the group.
func (p RESTStorageProvider) NewRESTStorage(
	apiResourceConfigSource serverstorage.APIResourceConfigSource,
	restOptionsGetter generic.RESTOptionsGetter,
) (genericapiserver.APIGroupInfo, error) {
	apiGroupInfo := genericapiserver.NewDefaultAPIGroupInfo(
		<group>.GroupName, legacyscheme.Scheme, legacyscheme.ParameterCodec, legacyscheme.Codecs)
	apiGroupInfo.NegotiatedSerializer = serializerutil.NewProtocolShieldSerializers(&legacyscheme.Codecs)

	storageMap, err := p.<version>Storage(apiResourceConfigSource, restOptionsGetter)
	if err != nil {
		return genericapiserver.APIGroupInfo{}, err
	}
	apiGroupInfo.VersionedResourcesStorageMap[<group><version>.SchemeGroupVersion.Version] = storageMap

	return apiGroupInfo, nil
}

func (p RESTStorageProvider) <version>Storage(
	apiResourceConfigSource serverstorage.APIResourceConfigSource,
	restOptionsGetter generic.RESTOptionsGetter,
) (map[string]rest.Storage, error) {
	storage := map[string]rest.Storage{}

	if resource := "<resource>"; apiResourceConfigSource.ResourceEnabled(<group><version>.SchemeGroupVersion.WithResource(resource)) {
		s, err := <kind>store.NewStorage(restOptionsGetter)
		if err != nil {
			return storage, err
		}
		storage[resource] = s.<Kind>
		storage[resource+"/status"] = s.Status
	}

	return storage, nil
}

// GroupName returns the API group name.
func (p RESTStorageProvider) GroupName() string {
	return <group>.GroupName
}
```

Notes:

- The storage map keys the subresources explicitly: `"<resource>"` and
  `"<resource>/status"` (plus `"<resource>/scale"` when scale is present).
- `NewProtocolShieldSerializers` and the `serializerutil` import follow the
  repository's existing group providers; reuse whatever the neighboring
  `rest/storage_*.go` uses rather than inventing a serializer.
- Wire this provider in the apiserver entry (see `references/file-map.md`).
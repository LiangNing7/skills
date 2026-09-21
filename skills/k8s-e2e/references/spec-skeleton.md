# Spec skeleton

Two files: the suite bootstrap and the feature specs. Both live under
`test/e2e/`. `<Kind>` is the resource, `<group>` the API group, `<module>` the
module path.

## Suite bootstrap (`test/e2e/e2e_test.go`)

```go
package e2e

import (
	"os"
	"testing"

	"k8s.io/client-go/tools/clientcmd"
	"sigs.k8s.io/controller-runtime/pkg/client"

	"<module>/pkg/generated/clientset/versioned"
)

var (
	clientset versioned.Interface
	k8sClient client.Client
)

// TestMain loads the cluster kubeconfig and builds the typed clientset once for all specs.
func TestMain(m *testing.M) {
	loadingRules := clientcmd.NewDefaultClientConfigLoadingRules()
	config, err := clientcmd.BuildConfigFromFlags("", loadingRules.GetDefaultFilename())
	if err != nil {
		os.Exit(1)
	}

	clientset, err = versioned.NewForConfig(config)
	if err != nil {
		os.Exit(1)
	}
	// ... optional controller-runtime client for generic reads/writes ...

	os.Exit(m.Run())
}
```

Use the repository's own kubeconfig conventions (its flag/env var for the
cluster address); the `loadingRules` shape above is illustrative.

## Feature spec (`test/e2e/<kind>_test.go`)

```go
package e2e

import (
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"<module>/pkg/apis/<group>/v1beta1"
)

var _ = Describe("<Kind> reconcile", func() {
	var namespace string

	BeforeEach(func() {
		namespace = uniqueNamespace() // helper that creates + returns a fresh namespace
		DeferCleanup(func() {
			// delete the namespace; tolerate already-deleted on re-runs
		})
	})

	It("converges to the expected terminal state", func() {
		obj := &v1beta1.<Kind>{
			ObjectMeta: metav1.ObjectMeta{Name: "sample", Namespace: namespace},
			Spec: v1beta1.<Kind>Spec{
				// ... minimal valid spec ...
			},
		}
		_, err := clientset.<Group>V1beta1().<Kinds>(namespace).Create(ctx, obj, metav1.CreateOptions{})
		Expect(err).NotTo(HaveOccurred())

		Eventually(func(g Gomega) {
			got, err := clientset.<Group>V1beta1().<Kinds>(namespace).Get(ctx, "sample", metav1.GetOptions{})
			g.Expect(err).NotTo(HaveOccurred())
			g.Expect(got.Status.Phase).To(Equal(v1beta1.<Kind>PhaseRunning))
			g.Expect(conditions.IsTrue(got, v1beta1.ReadyCondition)).To(BeTrue())
		}).WithTimeout(2 * time.Minute).WithPolling(2 * time.Second).Should(Succeed())
	})
})
```

## Rules

- Assert with `Eventually` (an explicit `WithTimeout`/`WithPolling`) against the
  live cluster — the controller reconciles asynchronously; a create-response
  check will race it.
- Isolate every spec in its own namespace so parallel runs do not collide.
- Clean up via `DeferCleanup`/`AfterEach`, and make cleanup idempotent (tolerate
  `NotFound`).
- Import only the generated client and the versioned types; never reach into the
  controller or apiserver internals.
- Keep the terminal-state assertion on `status.phase`/conditions/
  `observedGeneration`, not on controller implementation details.
- Some suites wrap ginkgo with `sigs.k8s.io/e2e-framework` for env/feature
  helpers; the ginkgo + gomega core above is the portable convention and is what
  the framework is built on.
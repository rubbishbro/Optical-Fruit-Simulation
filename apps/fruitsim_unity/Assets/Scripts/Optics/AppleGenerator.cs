using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Programmatic entry point for a single authored Blender apple.
    /// Batch generation can call this same method with a sequence of seeds.
    /// </summary>
    public sealed class AppleGenerator : MonoBehaviour
    {
        [SerializeField] private GameObject sourcePrefab;
        [SerializeField] private string resourcePath = "FruitsimBlenderRig";

        public AppleGenerationCapabilities Capabilities { get; } = new AppleGenerationCapabilities();

        public AppleInstance GenerateApple(
            int seed,
            AppleGeometryParameters geometry,
            AppleVisualMaterial visualMaterial,
            ApplePhysicalProperties physical,
            ApplePose pose)
        {
            return GenerateApple(new AppleGenerationRequest
            {
                seed = seed,
                geometry = geometry ?? new AppleGeometryParameters(),
                visualMaterial = visualMaterial ?? new AppleVisualMaterial(),
                physical = physical ?? new ApplePhysicalProperties(),
                pose = pose ?? new ApplePose(),
            });
        }

        public AppleInstance GenerateApple(AppleGenerationRequest request)
        {
            if (request == null) throw new System.ArgumentNullException(nameof(request));
            AppleGenerationRequest snapshot = AppleRequestIdentity.Snapshot(request);
            GameObject prefab = sourcePrefab != null ? sourcePrefab : Resources.Load<GameObject>(resourcePath);
            if (prefab == null)
                throw new MissingReferenceException($"Apple source prefab is missing: Resources/{resourcePath}");

            GameObject container = Instantiate(prefab, transform);
            string sampleId = AppleRequestIdentity.CreateSampleId(snapshot);
            container.name = $"FruitsimApple_{sampleId.Substring(sampleId.Length - 12)}";
            Transform apple = FindChild(container.transform, "BlenderApple");
            if (apple == null)
            {
                Destroy(container);
                throw new MissingReferenceException("The authored Blender rig does not contain BlenderApple.");
            }

            apple.name = "GeneratedApple";
            apple.localScale = Vector3.one * Mathf.Max(0.01f, snapshot.geometry.scale);
            apple.localPosition = snapshot.pose.position;
            apple.localRotation = Quaternion.Euler(snapshot.pose.eulerAngles);

            AppleInstance instance = new AppleInstance
            {
                sampleId = sampleId,
                seed = snapshot.seed,
                geometry = snapshot.geometry,
                visualMaterial = snapshot.visualMaterial,
                physical = snapshot.physical,
                pose = snapshot.pose,
                unityObject = apple.gameObject,
                containerObject = container,
            };
            ApplyVisualMaterial(apple, snapshot.visualMaterial, instance);
            return instance;
        }

        public void DestroyApple(AppleInstance instance)
        {
            if (instance == null) return;
            if (instance.containerObject != null) DestroyOwnedObject(instance.containerObject);
            foreach (Material material in instance.ReleaseOwnedRuntimeMaterials())
                if (material != null) DestroyOwnedObject(material);
            instance.unityObject = null;
            instance.containerObject = null;
        }

        private static Transform FindChild(Transform root, string name)
        {
            foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
                if (child.name == name) return child;
            return null;
        }

        private static void ApplyVisualMaterial(Transform apple, AppleVisualMaterial visual, AppleInstance owner)
        {
            Shader shader = Resources.Load<Shader>("FruitsimSolid");
            if (shader == null) return;
            foreach (Renderer renderer in apple.GetComponentsInChildren<Renderer>(true))
            {
                Material material = new Material(shader)
                {
                    name = $"GeneratedAppleMaterial_{visual.roughness:0.###}",
                    color = visual.color,
                };
                material.SetColor("_Color", visual.color);
                renderer.sharedMaterial = material;
                owner.TrackOwnedRuntimeMaterial(material);
            }
        }

        private static void DestroyOwnedObject(Object value)
        {
            if (Application.isPlaying) Destroy(value);
            else DestroyImmediate(value);
        }
    }
}

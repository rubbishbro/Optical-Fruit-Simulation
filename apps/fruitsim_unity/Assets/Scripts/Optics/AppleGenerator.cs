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
            GameObject prefab = sourcePrefab != null ? sourcePrefab : Resources.Load<GameObject>(resourcePath);
            if (prefab == null)
                throw new MissingReferenceException($"Apple source prefab is missing: Resources/{resourcePath}");

            GameObject container = Instantiate(prefab, transform);
            container.name = $"FruitsimApple_{request.seed:D10}";
            Transform apple = FindChild(container.transform, "BlenderApple");
            if (apple == null)
            {
                Destroy(container);
                throw new MissingReferenceException("The authored Blender rig does not contain BlenderApple.");
            }

            apple.name = "GeneratedApple";
            apple.localScale = Vector3.one * Mathf.Max(0.01f, request.geometry.scale);
            apple.localPosition = request.pose.position;
            apple.localRotation = Quaternion.Euler(request.pose.eulerAngles);
            ApplyVisualMaterial(apple, request.visualMaterial);

            return new AppleInstance
            {
                sampleId = $"unity-apple-{request.seed:D10}",
                seed = request.seed,
                geometry = request.geometry,
                visualMaterial = request.visualMaterial,
                physical = request.physical,
                pose = request.pose,
                unityObject = apple.gameObject,
                containerObject = container,
            };
        }

        public void DestroyApple(AppleInstance instance)
        {
            if (instance != null && instance.containerObject != null)
                Destroy(instance.containerObject);
        }

        private static Transform FindChild(Transform root, string name)
        {
            foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
                if (child.name == name) return child;
            return null;
        }

        private static void ApplyVisualMaterial(Transform apple, AppleVisualMaterial visual)
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
            }
        }
    }
}

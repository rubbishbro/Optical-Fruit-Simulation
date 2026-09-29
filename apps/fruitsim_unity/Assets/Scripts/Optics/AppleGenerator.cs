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
                visualMaterial = visualMaterial ?? AppleVisualMaterial.LoadBlenderDefaults(),
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
            HideAuthoredRingEmitters(container.transform);
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
                    name = $"GeneratedAppleMaterial_{owner.sampleId.Substring(owner.sampleId.Length - 12)}",
                    color = new Color(visual.color.r, visual.color.g, visual.color.b, 1.0f),
                };
                // Fruit skin is intentionally opaque. The old 0.48 alpha came
                // from a Blender geometry-debug scene, not the parameterized
                // presentation material used by Fruitsim.
                material.SetColor("_Color", new Color(visual.color.r, visual.color.g, visual.color.b, 1.0f));
                material.SetFloat("_Roughness", Mathf.Clamp01(visual.roughness));
                material.SetFloat("_Metallic", Mathf.Clamp01(visual.metallic));
                material.SetFloat("_SpecularIORLevel", Mathf.Clamp01(visual.specularIORLevel));
                material.SetFloat("_IOR", Mathf.Max(1.0f, visual.ior));
                material.SetFloat("_SpotDensity", Mathf.Clamp01(visual.spotDensity));
                material.SetFloat("_NormalStrength", Mathf.Clamp01(visual.normalStrength));
                material.SetFloat("_SkinTransmission", Mathf.Clamp01(visual.skinTransmission));
                material.SetFloat("_SpotSeed", StableMaterialSeed(owner.sampleId));
                renderer.sharedMaterial = material;
                owner.TrackOwnedRuntimeMaterial(material);
            }
        }

        private static void HideAuthoredRingEmitters(Transform root)
        {
            // The Blender rig contains a fixed authoring-time emitter layout.
            // Runtime lightCount is controlled by IlluminationRigController,
            // so the fixed meshes must not remain visible beside the dynamic
            // emitter pool.
            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                if (renderer.name.StartsWith("RingLampEmitter_", System.StringComparison.Ordinal))
                    renderer.enabled = false;
            }
        }

        private static float StableMaterialSeed(string sampleId)
        {
            unchecked
            {
                uint hash = 2166136261u;
                for (int index = 0; index < sampleId.Length; index++)
                    hash = (hash ^ sampleId[index]) * 16777619u;
                return (hash & 0x00ffffffu) / 16777215.0f;
            }
        }

        private static void DestroyOwnedObject(Object value)
        {
            if (Application.isPlaying) Destroy(value);
            else DestroyImmediate(value);
        }
    }
}

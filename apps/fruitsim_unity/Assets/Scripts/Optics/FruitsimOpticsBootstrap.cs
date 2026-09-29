using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Makes the optics demo usable in the current minimal SampleScene while
    /// still allowing a real apple generator to provide SetAppleRoot later.
    /// A scene-authored controller, when present, takes precedence.
    /// </summary>
    public static class FruitsimOpticsBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void CreateIfMissing()
        {
            if (Object.FindFirstObjectByType<IlluminationRigController>() != null)
                return;
            GameObject root = new GameObject("FruitsimOpticsExperiment");
            IlluminationRigController controller = root.AddComponent<IlluminationRigController>();
            root.AddComponent<IlluminationControlPanel>();
            Transform apple = CreateBlenderRig(controller, root);
            controller.SetAppleRoot(apple);
            controller.Mode = IlluminationMode.RingIllumination;
            ConfigureDemoCamera(CalculateCenter(apple));
        }

        private static Transform CreateBlenderRig(IlluminationRigController controller, GameObject experimentRoot)
        {
            AppleGenerator generator = experimentRoot.AddComponent<AppleGenerator>();
            FruitsimAppleGeneratorBridge bridge = experimentRoot.AddComponent<FruitsimAppleGeneratorBridge>();
            bridge.Initialize(generator);
            bridge.AppleChanged += instance =>
            {
                if (instance == null || instance.unityObject == null)
                {
                    controller.SetAppleRoot(null);
                    return;
                }
                controller.SetAppleRoot(instance.unityObject.transform);
                ConfigureDemoCamera(CalculateCenter(instance.unityObject.transform));
            };
            AppleInstance generated = generator.GenerateApple(
                20260920,
                new AppleGeometryParameters(),
                AppleVisualMaterial.LoadBlenderDefaults(),
                new ApplePhysicalProperties(),
                new ApplePose());
            ApplyBlenderMaterials(generated.containerObject.transform);
            bridge.AdoptApple(generated);
            controller.UseExternalSensorVisuals();
            return generated.unityObject.transform;
        }

        private static void ApplyBlenderMaterials(Transform root)
        {
            BlenderRigMaterialProfiles profiles = BlenderRigMaterialProfiles.Load();
            Material glass = CreateGlassMaterial("DetectorGlass_Migrated", profiles.detector_glass);
            Color authoredHousing = profiles.detector_housing.ColorOr(new Color(0.8f, 0.8f, 0.8f));
            Color displayHousing = new Color(authoredHousing.r * 0.25f, authoredHousing.g * 0.26f, authoredHousing.b * 0.28f, 1.0f);
            Material housing = CreateRigMaterial("DetectorHousing_Migrated", displayHousing, profiles.detector_housing.roughness, profiles.detector_housing.metallic, profiles.detector_housing.coat_weight);
            Material lampHousing = CreateRigMaterial("RingLampHousing_Material", new Color(0.22f, 0.24f, 0.28f), 0.62f, 0.0f, 0.05f);
            Material lampEmitter = CreateRigMaterial("RingLampEmitter_Material", new Color(0.42f, 0.06f, 0.01f), 0.28f, 0.0f, 0.0f, new Color(1.0f, 0.08f, 0.005f), 3.2f);
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            foreach (Renderer renderer in renderers)
            {
                // AppleGenerator has already applied the request snapshot to
                // the authored apple. Do not replace that runtime material
                // with a rig-wide fallback, otherwise Blender's migrated
                // Base Color/Roughness and WebGL UI values are lost.
                if (renderer.name == "BlenderApple" || renderer.name == "GeneratedApple")
                    continue;
                if (renderer.name == "DetectorGlass") renderer.sharedMaterial = glass;
                else if (renderer.name == "DetectorHousing") renderer.sharedMaterial = housing;
                else if (renderer.name.StartsWith("RingLampEmitter_")) renderer.sharedMaterial = lampEmitter;
                else renderer.sharedMaterial = lampHousing;
            }
        }

        private static Material CreateGlassMaterial(string name, BlenderPrincipledProfile profile)
        {
            Shader shader = Resources.Load<Shader>("FruitsimGlass");
            if (shader == null) throw new MissingReferenceException("Resources/FruitsimGlass.shader is required.");
            Material material = new Material(shader) { name = name };
            material.SetColor("_Color", profile.ColorOr(new Color(0.78f, 0.90f, 1.0f)));
            material.SetFloat("_Roughness", Mathf.Clamp01(profile.roughness));
            material.SetFloat("_IOR", Mathf.Max(1.0f, profile.ior));
            material.SetFloat("_Transmission", Mathf.Clamp01(profile.transmission));
            material.SetFloat("_Thickness", 0.24f);
            return material;
        }

        private static Material CreateRigMaterial(string name, Color color, float roughness, float metallic, float coatWeight, Color emission = default, float emissionStrength = 0.0f)
        {
            Shader shader = Resources.Load<Shader>("FruitsimRig");
            if (shader == null) throw new MissingReferenceException("Resources/FruitsimRig.shader is required.");
            Material material = new Material(shader) { name = name };
            material.SetColor("_Color", color);
            material.SetFloat("_Roughness", Mathf.Clamp01(roughness));
            material.SetFloat("_Metallic", Mathf.Clamp01(metallic));
            material.SetFloat("_CoatWeight", Mathf.Clamp01(coatWeight));
            material.SetColor("_EmissionColor", emission);
            material.SetFloat("_EmissionStrength", Mathf.Max(0.0f, emissionStrength));
            return material;
        }

        private static Vector3 CalculateCenter(Transform root)
        {
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return root.position;
            Bounds bounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++) bounds.Encapsulate(renderers[i].bounds);
            return bounds.center;
        }

        private static void ConfigureDemoCamera(Vector3 target)
        {
            Camera camera = Camera.main;
            if (camera == null) return;
            camera.gameObject.name = "FruitsimOrbitCamera";
            // Frame the whole Blender-authored instrument, not only the fruit.
            // The lower target keeps the detector and complete lamp ring visible
            // in the relatively short WebGL teaching viewport.
            Vector3 assemblyTarget = target + new Vector3(0.0f, -0.38f, 0.0f);
            camera.transform.position = assemblyTarget + new Vector3(4.25f, 2.65f, -6.8f);
            camera.transform.LookAt(assemblyTarget);
            camera.fieldOfView = 40.0f;
            camera.nearClipPlane = 0.05f;
            OrbitCameraController orbit = camera.GetComponent<OrbitCameraController>();
            if (orbit == null) orbit = camera.gameObject.AddComponent<OrbitCameraController>();
            orbit.Initialize(assemblyTarget, camera.transform.position);
        }
    }
}

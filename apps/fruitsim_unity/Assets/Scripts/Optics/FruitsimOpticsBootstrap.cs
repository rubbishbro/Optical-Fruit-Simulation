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
            AppleInstance generated = generator.GenerateApple(
                20260920,
                new AppleGeometryParameters(),
                new AppleVisualMaterial(),
                new ApplePhysicalProperties(),
                new ApplePose());
            ApplyBlenderMaterials(generated.containerObject.transform);
            controller.UseExternalSensorVisuals();
            return generated.unityObject.transform;
        }

        private static void ApplyBlenderMaterials(Transform root)
        {
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            foreach (Renderer renderer in renderers)
            {
                Color color = new Color(0.22f, 0.24f, 0.28f);
                if (renderer.name == "BlenderApple") color = new Color(0.48f, 0.035f, 0.025f);
                else if (renderer.name == "DetectorGlass") color = new Color(0.02f, 0.32f, 0.85f);
                else if (renderer.name == "DetectorHousing") color = new Color(0.035f, 0.055f, 0.085f);
                else if (renderer.name.StartsWith("RingLampEmitter_")) color = new Color(1.0f, 0.24f, 0.02f);
                renderer.sharedMaterial = CreateMaterial(renderer.name + "_Material", color);
            }
        }

        private static Material CreateMaterial(string name, Color color)
        {
            Shader shader = Resources.Load<Shader>("FruitsimSolid");
            if (shader == null) throw new MissingReferenceException("Resources/FruitsimSolid.shader is required.");
            Material material = new Material(shader) { name = name, color = color };
            material.SetColor("_Color", color);
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

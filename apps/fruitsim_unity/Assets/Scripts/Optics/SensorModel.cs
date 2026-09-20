using UnityEngine;
using UnityEngine.Rendering;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Visual sensor housing plus the finite circular aperture used by optics.
    /// The housing is presentation-only; OpticalConfiguration.sensor is the
    /// only part that should be passed to the Monte Carlo transport layer.
    /// </summary>
    public sealed class SensorModel : MonoBehaviour
    {
        [SerializeField] private float sensorRadius = 0.35f;
        [SerializeField] private float sensorVerticalOffset = 0.75f;
        [SerializeField, Range(1.0f, 180.0f)] private float sensorFOVDeg = 70.0f;
        [SerializeField] private bool useRatioScale = true;
        [SerializeField] private float sensorOffsetRatio = 0.18f;
        [SerializeField] private Material housingMaterial;
        [SerializeField] private Material apertureMaterial;

        private GameObject housing;
        private GameObject aperture;
        private float worldRadius;
        private float worldOffset;
        private Vector3 sensorCenter;
        private bool visualsAvailable;
        private bool visualsEnabled = true;

        public float SensorRadius { get => sensorRadius; set { sensorRadius = Mathf.Max(0.001f, value); } }
        public float SensorVerticalOffset { get => sensorVerticalOffset; set { sensorVerticalOffset = Mathf.Max(0.001f, value); } }
        public float SensorFOVDeg { get => sensorFOVDeg; set { sensorFOVDeg = Mathf.Clamp(value, 1.0f, 180.0f); } }
        public bool UseRatioScale { get => useRatioScale; set => useRatioScale = value; }
        public float SensorOffsetRatio { get => sensorOffsetRatio; set => sensorOffsetRatio = Mathf.Max(0.001f, value); }
        public float WorldRadius => worldRadius;
        public Vector3 SensorCenter => sensorCenter;
        public Vector3 Normal => transform.up;
        public bool VisualsEnabled
        {
            get => visualsEnabled;
            set
            {
                visualsEnabled = value;
                if (housing != null) housing.SetActive(value);
                if (aperture != null) aperture.SetActive(value);
            }
        }

        private void Awake()
        {
            visualsAvailable = SystemInfo.graphicsDeviceType != GraphicsDeviceType.Null;
        }

        public void Configure(Vector3 appleCenter, float ringPlaneY, float appleHeight)
        {
            worldRadius = Mathf.Max(0.001f, sensorRadius);
            worldOffset = Mathf.Max(0.001f, sensorVerticalOffset);
            if (useRatioScale)
            {
                worldRadius = Mathf.Max(0.001f, sensorRadius * appleHeight);
                worldOffset = Mathf.Max(0.001f, sensorOffsetRatio * appleHeight);
            }

            sensorCenter = new Vector3(
                appleCenter.x,
                ringPlaneY - worldOffset,
                appleCenter.z);
            transform.SetPositionAndRotation(sensorCenter, Quaternion.identity);
            if (!visualsAvailable || !visualsEnabled)
            {
                if (housing != null) housing.SetActive(false);
                if (aperture != null) aperture.SetActive(false);
                return;
            }
            EnsureVisuals();
            // Cylinder.fbx has a two-unit diameter, while Unity's generated
            // Cylinder primitive has a one-unit diameter. Keep the existing
            // visual dimensions without requiring a runtime CapsuleCollider.
            housing.transform.localScale = new Vector3(worldRadius * 1.25f, 0.18f, worldRadius * 1.25f);
            aperture.transform.localScale = new Vector3(worldRadius, 0.20f, worldRadius);
        }

        public SensorOpticalConfiguration GetOpticalConfiguration()
        {
            return new SensorOpticalConfiguration
            {
                center = sensorCenter,
                normal = Vector3.up,
                radius = worldRadius,
                fovDeg = sensorFOVDeg
            };
        }

        private void EnsureVisuals()
        {
            if (housing != null) return;
            housing = CreateCylinderVisual("SensorHousing_VisualOnly");
            housing.transform.SetParent(transform, false);
            AssignMaterial(housing, housingMaterial, new Color(0.12f, 0.14f, 0.17f));

            aperture = CreateCylinderVisual("SensorAperture_OpticalOnly");
            aperture.transform.SetParent(transform, false);
            AssignMaterial(aperture, apertureMaterial, new Color(0.03f, 0.45f, 0.8f));
        }

        private static GameObject CreateCylinderVisual(string name)
        {
            GameObject target = new GameObject(name);
            MeshFilter filter = target.AddComponent<MeshFilter>();
            filter.sharedMesh = Resources.GetBuiltinResource<Mesh>("Cylinder.fbx");
            target.AddComponent<MeshRenderer>();
            return target;
        }

        private static void AssignMaterial(GameObject target, Material material, Color fallback)
        {
            Renderer renderer = target.GetComponent<Renderer>();
            if (renderer == null) return;
            if (material != null)
            {
                renderer.sharedMaterial = material;
                return;
            }
            Shader shader = Resources.Load<Shader>("FruitsimSolid");
            if (shader == null)
            {
                Debug.LogWarning($"[Fruitsim Sensor] No compatible shader is available for {target.name}; continuing without a visual material.");
                return;
            }
            Material generated = new Material(shader)
            {
                color = fallback,
                name = target.name + "_Material"
            };
            renderer.sharedMaterial = generated;
        }
    }
}

using System;
using System.Collections.Generic;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Owns both the legacy coaxial layout and the new axisymmetric ring layout.
    /// Unity Light objects are visual previews only. GetOpticalConfiguration()
    /// is the transport-facing API and contains no GameObject references.
    /// </summary>
    public sealed class IlluminationRigController : MonoBehaviour
    {
        [Header("Scene references")]
        [SerializeField] private Transform appleRoot;
        [SerializeField] private SensorModel sensorModel;
        [SerializeField] private bool autoCreateVisuals = true;

        [Header("Mode")]
        [SerializeField] private IlluminationMode illuminationMode = IlluminationMode.Coaxial;

        [Header("Coaxial legacy layout")]
        [SerializeField] private float coaxialSourceHeightRatio = -0.55f;
        [SerializeField] private float coaxialOpticalPower = 1.0f;
        [SerializeField] private float coaxialBeamDivergenceDeg = 8.0f;

        [Header("Ring illumination")]
        [SerializeField, Min(1)] private int lightCount = 12;
        [SerializeField] private bool useRatioScale = true;
        [SerializeField] private float ringRadius = 1.0f;
        [SerializeField] private float ringRadiusRatio = 1.08f;
        [SerializeField] private float ringHeightOffset = -0.9f;
        [SerializeField] private float ringHeightRatio = -0.28f;
        [SerializeField, Range(0.0f, 89.0f)] private float lightTiltDeg = 35.0f;
        [SerializeField, Range(0.0f, 90.0f)] private float beamDivergenceDeg = 12.0f;
        [SerializeField] private float targetHeightOffset = 0.15f;
        [SerializeField] private float targetHeightRatio = 0.04f;
        [SerializeField, Min(0.0f)] private float totalOpticalPower = 1.0f;
        [SerializeField] private float sensorRadius = 0.35f;
        [SerializeField] private float sensorVerticalOffset = 0.75f;
        [SerializeField] private bool sensorUseRatioScale = true;
        [SerializeField] private float sensorOffsetRatio = 0.18f;
        [SerializeField, Range(1.0f, 180.0f)] private float sensorFOVDeg = 70.0f;
        [SerializeField] private bool enableHousingReflection = false;

        [Header("Debug visualization")]
        [SerializeField] private bool showDirectionRays = true;
        [SerializeField] private float directionRayLength = 1.4f;
        [SerializeField] private Color directionRayColor = new Color(1.0f, 0.35f, 0.05f, 0.8f);

        private Transform ringLightRig;
        private Transform coaxialLightRig;
        private Transform debugRayRig;
        private LineRenderer ringGuide;
        private readonly List<Light> ringLights = new List<Light>();
        private readonly List<LineRenderer> directionRays = new List<LineRenderer>();
        private OpticalConfiguration latestConfiguration;
        private bool dirty = true;

        public event Action<OpticalConfiguration> ConfigurationChanged;
        public IlluminationMode Mode { get => illuminationMode; set { illuminationMode = value; dirty = true; } }
        public int LightCount { get => lightCount; set { lightCount = Mathf.Max(1, value); dirty = true; } }
        public float RingRadius { get => ringRadius; set { ringRadius = Mathf.Max(0.001f, value); dirty = true; } }
        public bool UseRatioScale { get => useRatioScale; set { if (useRatioScale != value) { useRatioScale = value; dirty = true; } } }
        public float RingRadiusRatio { get => ringRadiusRatio; set { ringRadiusRatio = Mathf.Max(0.001f, value); dirty = true; } }
        public float RingHeightRatio { get => ringHeightRatio; set { ringHeightRatio = value; dirty = true; } }
        public float RingHeightOffset { get => ringHeightOffset; set { ringHeightOffset = value; dirty = true; } }
        public float LightTiltDeg { get => lightTiltDeg; set { lightTiltDeg = Mathf.Clamp(value, 0.0f, 89.0f); dirty = true; } }
        public float BeamDivergenceDeg { get => beamDivergenceDeg; set { beamDivergenceDeg = Mathf.Clamp(value, 0.0f, 90.0f); dirty = true; } }
        public float TargetHeightOffset { get => targetHeightOffset; set { targetHeightOffset = value; dirty = true; } }
        public float TargetHeightRatio { get => targetHeightRatio; set { targetHeightRatio = value; dirty = true; } }
        public float TotalOpticalPower { get => totalOpticalPower; set { totalOpticalPower = Mathf.Max(0.0f, value); dirty = true; } }
        public float SensorRadius { get => sensorRadius; set { sensorRadius = Mathf.Max(0.001f, value); dirty = true; } }
        public float SensorVerticalOffset { get => sensorVerticalOffset; set { sensorVerticalOffset = Mathf.Max(0.001f, value); dirty = true; } }
        public float SensorFOVDeg { get => sensorFOVDeg; set { sensorFOVDeg = Mathf.Clamp(value, 1.0f, 180.0f); dirty = true; } }
        public bool SensorUseRatioScale { get => sensorUseRatioScale; set { if (sensorUseRatioScale != value) { sensorUseRatioScale = value; dirty = true; } } }
        public float SensorOffsetRatio { get => sensorOffsetRatio; set { sensorOffsetRatio = Mathf.Max(0.001f, value); dirty = true; } }

        private void Awake()
        {
            if (sensorModel == null)
            {
                GameObject sensor = new GameObject("SensorRig");
                sensor.transform.SetParent(transform, false);
                sensorModel = sensor.AddComponent<SensorModel>();
            }
            dirty = true;
        }

        private void LateUpdate()
        {
            if (dirty) RebuildRig();
        }

        public void SetAppleRoot(Transform root)
        {
            appleRoot = root;
            dirty = true;
        }

        public OpticalConfiguration GetOpticalConfiguration()
        {
            if (dirty) RebuildRig();
            return latestConfiguration;
        }

        public void RebuildRig()
        {
            dirty = false;
            Bounds bounds = CalculateAppleBounds();
            Vector3 appleCenter = bounds.center;
            float appleHeight = Mathf.Max(0.001f, bounds.size.y);
            float appleRadius = Mathf.Max(0.001f, Mathf.Max(bounds.size.x, bounds.size.z) * 0.5f);
            float ringRadiusWorld = useRatioScale ? ringRadiusRatio * appleRadius : ringRadius;
            float ringOffsetWorld = useRatioScale ? ringHeightRatio * appleHeight : ringHeightOffset;
            float targetOffsetWorld = useRatioScale ? targetHeightRatio * appleHeight : targetHeightOffset;
            float ringY = appleCenter.y + ringOffsetWorld;
            Vector3 target = appleCenter + Vector3.up * targetOffsetWorld;

            EnsureRigs();
            BuildRingLights(appleCenter, ringY, ringRadiusWorld, target);
            BuildCoaxialVisual(appleCenter, appleHeight);
            sensorModel.SensorRadius = sensorRadius;
            sensorModel.SensorVerticalOffset = sensorVerticalOffset;
            sensorModel.SensorFOVDeg = sensorFOVDeg;
            sensorModel.UseRatioScale = sensorUseRatioScale;
            sensorModel.SensorOffsetRatio = sensorOffsetRatio;
            sensorModel.Configure(appleCenter, ringY, appleHeight);

            bool ringActive = illuminationMode == IlluminationMode.RingIllumination;
            ringLightRig.gameObject.SetActive(ringActive);
            coaxialLightRig.gameObject.SetActive(!ringActive);
            latestConfiguration = ringActive
                ? BuildRingConfiguration(appleCenter, ringY, ringRadiusWorld, target)
                : BuildCoaxialConfiguration(appleCenter, appleHeight);
            ConfigurationChanged?.Invoke(latestConfiguration);
        }

        private Bounds CalculateAppleBounds()
        {
            if (appleRoot == null)
                return new Bounds(transform.position, Vector3.one * 2.0f);
            Renderer[] renderers = appleRoot.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                return new Bounds(appleRoot.position, Vector3.one * 2.0f);
            Bounds result = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++) result.Encapsulate(renderers[i].bounds);
            return result;
        }

        private void EnsureRigs()
        {
            if (ringLightRig == null)
            {
                ringLightRig = new GameObject("RingLightRig").transform;
                ringLightRig.SetParent(transform, false);
            }
            if (coaxialLightRig == null)
            {
                coaxialLightRig = new GameObject("CoaxialLightRig").transform;
                coaxialLightRig.SetParent(transform, false);
            }
            if (debugRayRig == null)
            {
                debugRayRig = new GameObject("IlluminationDebugRays").transform;
                debugRayRig.SetParent(transform, false);
            }
            if (ringGuide == null)
            {
                GameObject guide = new GameObject("RingRadiusGuide");
                guide.transform.SetParent(ringLightRig, false);
                ringGuide = guide.AddComponent<LineRenderer>();
                ringGuide.loop = true;
                ringGuide.useWorldSpace = false;
                ringGuide.widthMultiplier = 0.012f;
                ringGuide.material = new Material(Shader.Find("Sprites/Default"));
                ringGuide.startColor = new Color(1.0f, 0.45f, 0.05f, 0.3f);
                ringGuide.endColor = ringGuide.startColor;
            }
        }

        private void BuildRingLights(Vector3 center, float ringY, float radius, Vector3 target)
        {
            ringLightRig.position = center;
            ClearChildrenExcept(ringLightRig, ringGuide != null ? ringGuide.transform : null);
            ClearChildren(debugRayRig);
            ringLights.Clear();
            directionRays.Clear();
            float tilt = lightTiltDeg * Mathf.Deg2Rad;
            ringGuide.positionCount = Mathf.Max(32, lightCount * 4);
            for (int i = 0; i < ringGuide.positionCount; i++)
            {
                float phi = 2.0f * Mathf.PI * i / ringGuide.positionCount;
                ringGuide.SetPosition(i, new Vector3(radius * Mathf.Cos(phi), 0.0f, radius * Mathf.Sin(phi)));
            }
            for (int i = 0; i < lightCount; i++)
            {
                float phi = 2.0f * Mathf.PI * i / lightCount;
                Vector3 position = center + new Vector3(radius * Mathf.Cos(phi), ringY - center.y, radius * Mathf.Sin(phi));
                Vector3 inward = new Vector3(target.x - position.x, 0.0f, target.z - position.z).normalized;
                if (inward.sqrMagnitude < 1.0e-6f)
                    inward = new Vector3(center.x - position.x, 0.0f, center.z - position.z).normalized;
                Vector3 direction = (inward * Mathf.Cos(tilt) + Vector3.up * Mathf.Sin(tilt)).normalized;
                GameObject visual = new GameObject($"Light_{i:00}");
                visual.transform.SetParent(ringLightRig, false);
                visual.transform.SetPositionAndRotation(position, Quaternion.LookRotation(direction, Vector3.up));
                Light spot = visual.AddComponent<Light>();
                spot.type = LightType.Spot;
                spot.range = appleHeightForVisual() * 2.5f;
                spot.spotAngle = Mathf.Clamp(beamDivergenceDeg * 2.0f, 1.0f, 179.0f);
                spot.intensity = lightCount > 0 ? totalOpticalPower / lightCount : 0.0f;
                spot.color = new Color(1.0f, 0.12f, 0.02f);
                ringLights.Add(spot);
                if (showDirectionRays) AddDebugRay(position, position + direction * directionRayLength);
            }
            debugRayRig.gameObject.SetActive(showDirectionRays && illuminationMode == IlluminationMode.RingIllumination);
        }

        private float appleHeightForVisual()
        {
            return Mathf.Max(1.0f, CalculateAppleBounds().size.y);
        }

        private void AddDebugRay(Vector3 start, Vector3 end)
        {
            GameObject rayObject = new GameObject("DirectionRay");
            rayObject.transform.SetParent(debugRayRig, false);
            LineRenderer line = rayObject.AddComponent<LineRenderer>();
            line.positionCount = 2;
            line.SetPosition(0, start);
            line.SetPosition(1, end);
            line.useWorldSpace = true;
            line.widthMultiplier = 0.018f;
            line.material = new Material(Shader.Find("Sprites/Default"));
            line.startColor = directionRayColor;
            line.endColor = directionRayColor;
            directionRays.Add(line);
        }

        private void BuildCoaxialVisual(Vector3 center, float appleHeight)
        {
            ClearChildren(coaxialLightRig);
            GameObject source = new GameObject("CoaxialSource");
            source.transform.SetParent(coaxialLightRig, false);
            source.transform.position = center + Vector3.up * (coaxialSourceHeightRatio * appleHeight);
            source.transform.rotation = Quaternion.LookRotation(Vector3.up);
            Light light = source.AddComponent<Light>();
            light.type = LightType.Spot;
            light.range = appleHeight * 2.5f;
            light.spotAngle = coaxialBeamDivergenceDeg * 2.0f;
            light.intensity = coaxialOpticalPower;
            light.color = new Color(1.0f, 0.12f, 0.02f);
        }

        private OpticalConfiguration BuildRingConfiguration(Vector3 center, float ringY, float radius, Vector3 target)
        {
            PhotonSourceConfiguration[] sources = new PhotonSourceConfiguration[lightCount];
            float tilt = lightTiltDeg * Mathf.Deg2Rad;
            float powerPerLight = lightCount > 0 ? totalOpticalPower / lightCount : 0.0f;
            for (int i = 0; i < lightCount; i++)
            {
                float phi = 2.0f * Mathf.PI * i / lightCount;
                Vector3 position = center + new Vector3(radius * Mathf.Cos(phi), ringY - center.y, radius * Mathf.Sin(phi));
                Vector3 inward = new Vector3(target.x - position.x, 0.0f, target.z - position.z).normalized;
                if (inward.sqrMagnitude < 1.0e-6f)
                    inward = new Vector3(center.x - position.x, 0.0f, center.z - position.z).normalized;
                Vector3 direction = (inward * Mathf.Cos(tilt) + Vector3.up * Mathf.Sin(tilt)).normalized;
                sources[i] = new PhotonSourceConfiguration
                {
                    position = position,
                    direction = direction,
                    opticalPower = powerPerLight,
                    beamDivergenceDeg = beamDivergenceDeg,
                    sourceIndex = i
                };
            }
            return new OpticalConfiguration
            {
                mode = IlluminationMode.RingIllumination,
                sources = sources,
                sensor = sensorModel.GetOpticalConfiguration(),
                totalOpticalPower = totalOpticalPower,
                enableHousingReflection = enableHousingReflection
            };
        }

        private OpticalConfiguration BuildCoaxialConfiguration(Vector3 center, float appleHeight)
        {
            Vector3 position = center + Vector3.up * (coaxialSourceHeightRatio * appleHeight);
            return new OpticalConfiguration
            {
                mode = IlluminationMode.Coaxial,
                sources = new[]
                {
                    new PhotonSourceConfiguration
                    {
                        position = position,
                        direction = Vector3.up,
                        opticalPower = coaxialOpticalPower,
                        beamDivergenceDeg = coaxialBeamDivergenceDeg,
                        sourceIndex = 0
                    }
                },
                sensor = sensorModel.GetOpticalConfiguration(),
                totalOpticalPower = coaxialOpticalPower,
                enableHousingReflection = enableHousingReflection
            };
        }

        private static void ClearChildren(Transform parent)
        {
            for (int i = parent.childCount - 1; i >= 0; i--)
                Destroy(parent.GetChild(i).gameObject);
        }

        private static void ClearChildrenExcept(Transform parent, Transform keep)
        {
            for (int i = parent.childCount - 1; i >= 0; i--)
            {
                if (parent.GetChild(i) != keep)
                    Destroy(parent.GetChild(i).gameObject);
            }
        }
    }
}

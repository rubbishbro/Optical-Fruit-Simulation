using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

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
        [SerializeField, Range(400.0f, 1100.0f)] private float wavelengthNm = 700.0f;

        private Transform ringLightRig;
        private Transform coaxialLightRig;
        private Transform debugRayRig;
        private LineRenderer ringGuide;
        private Material debugLineMaterial;
        private Light coaxialLight;
        private readonly List<Light> ringLights = new List<Light>();
        private readonly List<LineRenderer> directionRays = new List<LineRenderer>();
        private Renderer[] appleRenderers = Array.Empty<Renderer>();
        private bool appleRenderersDirty = true;
        private bool visualsAvailable;
        private OpticalConfiguration latestConfiguration;
        private bool dirty = true;
        private int rebuildCount;
        private float lastRebuildMilliseconds;

        public event Action<OpticalConfiguration> ConfigurationChanged;
        public IlluminationMode Mode { get => illuminationMode; set { if (illuminationMode != value) { illuminationMode = value; dirty = true; } } }
        public int LightCount { get => lightCount; set { int next = Mathf.Max(1, value); if (lightCount != next) { lightCount = next; dirty = true; } } }
        public float RingRadius { get => ringRadius; set { float next = Mathf.Max(0.001f, value); if (!Mathf.Approximately(ringRadius, next)) { ringRadius = next; dirty = true; } } }
        public bool UseRatioScale { get => useRatioScale; set { if (useRatioScale != value) { useRatioScale = value; dirty = true; } } }
        public float RingRadiusRatio { get => ringRadiusRatio; set { float next = Mathf.Max(0.001f, value); if (!Mathf.Approximately(ringRadiusRatio, next)) { ringRadiusRatio = next; dirty = true; } } }
        public float RingHeightRatio { get => ringHeightRatio; set { if (!Mathf.Approximately(ringHeightRatio, value)) { ringHeightRatio = value; dirty = true; } } }
        public float RingHeightOffset { get => ringHeightOffset; set { if (!Mathf.Approximately(ringHeightOffset, value)) { ringHeightOffset = value; dirty = true; } } }
        public float LightTiltDeg { get => lightTiltDeg; set { float next = Mathf.Clamp(value, 0.0f, 89.0f); if (!Mathf.Approximately(lightTiltDeg, next)) { lightTiltDeg = next; dirty = true; } } }
        public float BeamDivergenceDeg { get => beamDivergenceDeg; set { float next = Mathf.Clamp(value, 0.0f, 90.0f); if (!Mathf.Approximately(beamDivergenceDeg, next)) { beamDivergenceDeg = next; dirty = true; } } }
        public float TargetHeightOffset { get => targetHeightOffset; set { if (!Mathf.Approximately(targetHeightOffset, value)) { targetHeightOffset = value; dirty = true; } } }
        public float TargetHeightRatio { get => targetHeightRatio; set { if (!Mathf.Approximately(targetHeightRatio, value)) { targetHeightRatio = value; dirty = true; } } }
        public float TotalOpticalPower { get => totalOpticalPower; set { float next = Mathf.Max(0.0f, value); if (!Mathf.Approximately(totalOpticalPower, next)) { totalOpticalPower = next; dirty = true; } } }
        public float SensorRadius { get => sensorRadius; set { float next = Mathf.Max(0.001f, value); if (!Mathf.Approximately(sensorRadius, next)) { sensorRadius = next; dirty = true; } } }
        public float SensorVerticalOffset { get => sensorVerticalOffset; set { float next = Mathf.Max(0.001f, value); if (!Mathf.Approximately(sensorVerticalOffset, next)) { sensorVerticalOffset = next; dirty = true; } } }
        public float SensorFOVDeg { get => sensorFOVDeg; set { float next = Mathf.Clamp(value, 1.0f, 180.0f); if (!Mathf.Approximately(sensorFOVDeg, next)) { sensorFOVDeg = next; dirty = true; } } }
        public bool SensorUseRatioScale { get => sensorUseRatioScale; set { if (sensorUseRatioScale != value) { sensorUseRatioScale = value; dirty = true; } } }
        public float SensorOffsetRatio { get => sensorOffsetRatio; set { float next = Mathf.Max(0.001f, value); if (!Mathf.Approximately(sensorOffsetRatio, next)) { sensorOffsetRatio = next; dirty = true; } } }
        public int RebuildCount => rebuildCount;
        public float LastRebuildMilliseconds => lastRebuildMilliseconds;
        public int PooledLightCount => ringLights.Count + (coaxialLight == null ? 0 : 1);
        public int PooledRayCount => directionRays.Count;

        public void UseExternalSensorVisuals()
        {
            if (sensorModel != null) sensorModel.VisualsEnabled = false;
        }

        [Serializable]
        private sealed class WebOpticalParameters
        {
            public float wavelength_nm;
            public float ring_radius_ratio;
            public float ring_height_ratio;
            public float incident_angle_deg;
            public float beam_divergence_deg;
            public float optical_power;
            public float sensor_radius_ratio;
            public float sensor_offset_ratio;
            public float sensor_fov_deg;
            public bool show_rays;
        }

        /// <summary>Entry point used by the surrounding WebGL research UI.</summary>
        public void ApplyWebParameters(string json)
        {
            WebOpticalParameters parameters = JsonUtility.FromJson<WebOpticalParameters>(json);
            if (parameters == null) return;
            wavelengthNm = Mathf.Clamp(parameters.wavelength_nm, 400.0f, 1100.0f);
            RingRadiusRatio = parameters.ring_radius_ratio;
            RingHeightRatio = parameters.ring_height_ratio;
            LightTiltDeg = parameters.incident_angle_deg;
            BeamDivergenceDeg = parameters.beam_divergence_deg;
            TotalOpticalPower = parameters.optical_power;
            SensorRadius = parameters.sensor_radius_ratio;
            SensorOffsetRatio = parameters.sensor_offset_ratio;
            SensorFOVDeg = parameters.sensor_fov_deg;
            showDirectionRays = parameters.show_rays;
            directionRayColor = WavelengthToDisplayColor(wavelengthNm);
            UpdateAuthoredEmitterColor(directionRayColor);
            dirty = true;
        }

        private void Awake()
        {
            visualsAvailable = SystemInfo.graphicsDeviceType != GraphicsDeviceType.Null;
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
            appleRenderersDirty = true;
            dirty = true;
        }

        public void MarkGeometryDirty()
        {
            appleRenderersDirty = true;
            dirty = true;
        }

        public OpticalConfiguration GetOpticalConfiguration()
        {
            if (dirty) RebuildRig();
            return latestConfiguration;
        }

        public void RebuildRig()
        {
            float rebuildStart = Time.realtimeSinceStartup;
            dirty = false;
            rebuildCount++;
            Bounds bounds = CalculateAppleBounds();
            Vector3 appleCenter = bounds.center;
            float appleHeight = Mathf.Max(0.001f, bounds.size.y);
            float appleRadius = Mathf.Max(0.001f, Mathf.Max(bounds.size.x, bounds.size.z) * 0.5f);
            float ringRadiusWorld = useRatioScale ? ringRadiusRatio * appleRadius : ringRadius;
            float ringOffsetWorld = useRatioScale ? ringHeightRatio * appleHeight : ringHeightOffset;
            float targetOffsetWorld = useRatioScale ? targetHeightRatio * appleHeight : targetHeightOffset;
            float ringY = appleCenter.y + ringOffsetWorld;
            Vector3 target = appleCenter + Vector3.up * targetOffsetWorld;

            if (visualsAvailable && autoCreateVisuals)
            {
                EnsureRigs();
                if (illuminationMode == IlluminationMode.RingIllumination)
                {
                    BuildRingLights(appleCenter, ringY, ringRadiusWorld, target, appleHeight);
                }
                else
                {
                    ringLightRig.gameObject.SetActive(false);
                    debugRayRig.gameObject.SetActive(false);
                }
                BuildCoaxialVisual(appleCenter, appleHeight);
            }
            sensorModel.SensorRadius = sensorRadius;
            sensorModel.SensorVerticalOffset = sensorVerticalOffset;
            sensorModel.SensorFOVDeg = sensorFOVDeg;
            sensorModel.UseRatioScale = sensorUseRatioScale;
            sensorModel.SensorOffsetRatio = sensorOffsetRatio;
            sensorModel.Configure(appleCenter, ringY, appleHeight);

            bool ringActive = illuminationMode == IlluminationMode.RingIllumination;
            if (visualsAvailable && autoCreateVisuals)
            {
                ringLightRig.gameObject.SetActive(ringActive);
                coaxialLightRig.gameObject.SetActive(!ringActive);
            }
            latestConfiguration = ringActive
                ? BuildRingConfiguration(appleCenter, ringY, ringRadiusWorld, target)
                : BuildCoaxialConfiguration(appleCenter, appleHeight);
            ConfigurationChanged?.Invoke(latestConfiguration);
            lastRebuildMilliseconds = (Time.realtimeSinceStartup - rebuildStart) * 1000.0f;
        }

        private Bounds CalculateAppleBounds()
        {
            if (appleRoot == null)
                return new Bounds(transform.position, Vector3.one * 2.0f);
            if (appleRenderersDirty)
            {
                appleRenderers = appleRoot.GetComponentsInChildren<Renderer>();
                appleRenderersDirty = false;
            }
            if (appleRenderers.Length == 0)
                return new Bounds(appleRoot.position, Vector3.one * 2.0f);
            Bounds result = appleRenderers[0].bounds;
            for (int i = 1; i < appleRenderers.Length; i++) result.Encapsulate(appleRenderers[i].bounds);
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
                debugLineMaterial = CreateOptionalMaterial("Sprites/Default", "Fruitsim_DebugLineMaterial");
                if (debugLineMaterial != null) ringGuide.sharedMaterial = debugLineMaterial;
                ringGuide.startColor = new Color(1.0f, 0.45f, 0.05f, 0.3f);
                ringGuide.endColor = ringGuide.startColor;
            }
        }

        private void BuildRingLights(Vector3 center, float ringY, float radius, Vector3 target, float appleHeight)
        {
            ringLightRig.position = center;
            Color displayColor = WavelengthToDisplayColor(wavelengthNm);
            displayColor.a = 0.88f;
            ringGuide.startColor = new Color(displayColor.r, displayColor.g, displayColor.b, 0.34f);
            ringGuide.endColor = ringGuide.startColor;
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
                Light spot = GetOrCreateRingLight(i);
                GameObject visual = spot.gameObject;
                visual.transform.SetPositionAndRotation(position, Quaternion.LookRotation(direction, Vector3.up));
                visual.SetActive(true);
                spot.type = LightType.Spot;
                spot.range = Mathf.Max(1.0f, appleHeight) * 2.5f;
                spot.spotAngle = Mathf.Clamp(beamDivergenceDeg * 2.0f, 1.0f, 179.0f);
                spot.intensity = lightCount > 0 ? totalOpticalPower / lightCount : 0.0f;
                spot.color = displayColor;
                LineRenderer ray = GetOrCreateDirectionRay(i);
                ray.gameObject.SetActive(showDirectionRays);
                ray.startColor = displayColor;
                ray.endColor = displayColor;
                if (showDirectionRays)
                {
                    ray.SetPosition(0, position);
                    ray.SetPosition(1, position + direction * directionRayLength);
                }
            }
            for (int i = lightCount; i < ringLights.Count; i++) ringLights[i].gameObject.SetActive(false);
            for (int i = lightCount; i < directionRays.Count; i++) directionRays[i].gameObject.SetActive(false);
            debugRayRig.gameObject.SetActive(showDirectionRays && illuminationMode == IlluminationMode.RingIllumination);
        }

        private Light GetOrCreateRingLight(int index)
        {
            while (ringLights.Count <= index)
            {
                GameObject visual = new GameObject($"Light_{ringLights.Count:00}");
                visual.transform.SetParent(ringLightRig, false);
                ringLights.Add(visual.AddComponent<Light>());
            }
            return ringLights[index];
        }

        private LineRenderer GetOrCreateDirectionRay(int index)
        {
            while (directionRays.Count <= index)
            {
                GameObject rayObject = new GameObject($"DirectionRay_{directionRays.Count:00}");
                rayObject.transform.SetParent(debugRayRig, false);
                LineRenderer line = rayObject.AddComponent<LineRenderer>();
                line.positionCount = 2;
                line.useWorldSpace = true;
                line.widthMultiplier = 0.018f;
                if (debugLineMaterial != null) line.sharedMaterial = debugLineMaterial;
                line.startColor = directionRayColor;
                line.endColor = directionRayColor;
                directionRays.Add(line);
            }
            return directionRays[index];
        }

        private void BuildCoaxialVisual(Vector3 center, float appleHeight)
        {
            if (coaxialLight == null)
            {
                GameObject source = new GameObject("CoaxialSource");
                source.transform.SetParent(coaxialLightRig, false);
                coaxialLight = source.AddComponent<Light>();
            }
            GameObject sourceObject = coaxialLight.gameObject;
            sourceObject.transform.position = center + Vector3.up * (coaxialSourceHeightRatio * appleHeight);
            sourceObject.transform.rotation = Quaternion.LookRotation(Vector3.up);
            sourceObject.SetActive(true);
            coaxialLight.type = LightType.Spot;
            coaxialLight.range = appleHeight * 2.5f;
            coaxialLight.spotAngle = coaxialBeamDivergenceDeg * 2.0f;
            coaxialLight.intensity = coaxialOpticalPower;
            coaxialLight.color = new Color(1.0f, 0.12f, 0.02f);
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

        private static Material CreateOptionalMaterial(string shaderName, string materialName)
        {
            Shader shader = Shader.Find(shaderName);
            if (shader == null) return null;
            return new Material(shader) { name = materialName };
        }

        private static Color WavelengthToDisplayColor(float wavelength)
        {
            // Visible wavelengths use an approximate display colour. NIR is
            // intentionally shown as muted crimson because a monitor cannot
            // emit 780–1100 nm; the UI labels this as false colour.
            if (wavelength >= 780.0f) return new Color(0.55f, 0.08f, 0.12f, 0.88f);
            float r = 0.0f, g = 0.0f, b = 0.0f;
            if (wavelength < 440.0f) { r = -(wavelength - 440.0f) / 60.0f; b = 1.0f; }
            else if (wavelength < 490.0f) { g = (wavelength - 440.0f) / 50.0f; b = 1.0f; }
            else if (wavelength < 510.0f) { g = 1.0f; b = -(wavelength - 510.0f) / 20.0f; }
            else if (wavelength < 580.0f) { r = (wavelength - 510.0f) / 70.0f; g = 1.0f; }
            else if (wavelength < 645.0f) { r = 1.0f; g = -(wavelength - 645.0f) / 65.0f; }
            else { r = 1.0f; }
            return new Color(Mathf.Clamp01(r), Mathf.Clamp01(g), Mathf.Clamp01(b), 0.88f);
        }

        private static void UpdateAuthoredEmitterColor(Color color)
        {
            Renderer[] renderers = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            foreach (Renderer renderer in renderers)
            {
                if (!renderer.name.StartsWith("RingLampEmitter_", StringComparison.Ordinal)) continue;
                renderer.material.color = color;
                renderer.material.SetColor("_Color", color);
            }
        }
    }
}

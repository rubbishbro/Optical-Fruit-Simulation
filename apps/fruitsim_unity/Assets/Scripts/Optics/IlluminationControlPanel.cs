using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Lightweight runtime control panel. It intentionally uses Unity IMGUI so
    /// the scene does not need a hand-authored Canvas before the experiment can
    /// be used. It can later be replaced by a UGUI panel using the same public
    /// controller properties.
    /// </summary>
    public sealed class IlluminationControlPanel : MonoBehaviour
    {
        [SerializeField] private IlluminationRigController controller;
        [SerializeField] private Rect panelRect = new Rect(18.0f, 18.0f, 330.0f, 640.0f);
        private bool visible = true;
        private readonly Dictionary<string, string> numericBuffers = new Dictionary<string, string>();

        private void Awake()
        {
            if (controller == null) controller = FindFirstObjectByType<IlluminationRigController>();
#if UNITY_WEBGL && !UNITY_EDITOR
            visible = false;
#endif
        }

        private void OnGUI()
        {
            if (controller == null) return;
            if (GUI.Button(new Rect(18.0f, 18.0f, 100.0f, 28.0f), visible ? "Hide optics" : "Show optics"))
                visible = !visible;
            if (!visible) return;
            panelRect.y = 54.0f;
            GUILayout.BeginArea(panelRect, GUI.skin.box);
            GUILayout.Label("Illumination control", GUI.skin.GetStyle("boldLabel"));
            int mode = GUILayout.SelectionGrid((int)controller.Mode,
                new[] { "Coaxial", "RingIllumination" }, 1);
            if (mode != (int)controller.Mode) controller.Mode = (IlluminationMode)mode;
            if (controller.Mode == IlluminationMode.RingIllumination)
            {
                controller.LightCount = IntSlider("Light Count", controller.LightCount, 1, 64);
                controller.UseRatioScale = GUILayout.Toggle(controller.UseRatioScale,
                    "Use apple-relative dimensions");
                if (controller.UseRatioScale)
                {
                    controller.RingRadiusRatio = Slider("Ring Radius Ratio", controller.RingRadiusRatio, 0.05f, 1.5f);
                    controller.RingHeightRatio = Slider("Ring Height Ratio", controller.RingHeightRatio, -1.0f, 0.25f);
                    controller.TargetHeightRatio = Slider("Target Height Ratio", controller.TargetHeightRatio, -0.5f, 0.5f);
                }
                else
                {
                    controller.RingRadius = Slider("Ring Radius", controller.RingRadius, 0.05f, 5.0f);
                    controller.RingHeightOffset = Slider("Ring Height Offset", controller.RingHeightOffset, -5.0f, 1.0f);
                    controller.TargetHeightOffset = Slider("Target Height Offset", controller.TargetHeightOffset, -2.0f, 2.0f);
                }
                controller.LightTiltDeg = Slider("Light Tilt / Incident Angle", controller.LightTiltDeg, 0.0f, 89.0f);
                controller.BeamDivergenceDeg = Slider("Beam Divergence", controller.BeamDivergenceDeg, 0.0f, 90.0f);
                controller.TotalOpticalPower = Slider("Total Optical Power", controller.TotalOpticalPower, 0.0f, 10.0f);
                controller.SensorUseRatioScale = controller.UseRatioScale;
                if (controller.UseRatioScale)
                {
                    controller.SensorRadius = Slider("Sensor Radius Ratio", controller.SensorRadius, 0.01f, 0.5f);
                    controller.SensorOffsetRatio = Slider("Sensor Offset Ratio", controller.SensorOffsetRatio, 0.01f, 0.75f);
                }
                else
                {
                    controller.SensorRadius = Slider("Sensor Radius", controller.SensorRadius, 0.01f, 2.0f);
                    controller.SensorVerticalOffset = Slider("Sensor Vertical Offset", controller.SensorVerticalOffset, 0.01f, 5.0f);
                }
                controller.SensorFOVDeg = Slider("Sensor FOV", controller.SensorFOVDeg, 1.0f, 180.0f);
                if (GUILayout.Button("Rebuild rig")) controller.RebuildRig();
            }
            else
            {
                GUILayout.Label("Legacy coaxial layout active.");
                GUILayout.Label("Light axis, apple center and sensor remain collinear.");
            }
            GUILayout.Space(8.0f);
            GUILayout.Label($"Rig rebuilds: {controller.RebuildCount}");
            GUILayout.Label($"Lights/rays/emitters: {controller.PooledLightCount}/{controller.PooledRayCount}/{controller.ActiveRingEmitterCount}");
            GUILayout.Label($"Last rebuild: {controller.LastRebuildMilliseconds:0.###} ms");
            GUILayout.EndArea();
        }

        private int IntSlider(string label, int value, int min, int max)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label($"{label}: {value}", GUILayout.Width(170.0f));
            int sliderValue = Mathf.RoundToInt(GUILayout.HorizontalSlider(value, min, max));
            GUILayout.EndHorizontal();
            return IntegerField(label, sliderValue, min, max);
        }

        private float Slider(string label, float value, float min, float max)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label($"{label}: {value:0.###}", GUILayout.Width(170.0f));
            float sliderValue = GUILayout.HorizontalSlider(value, min, max);
            GUILayout.EndHorizontal();
            return FloatField(label, sliderValue, min, max);
        }

        private int IntegerField(string key, int value, int min, int max)
        {
            string controlName = $"FruitsimInteger_{key}";
            if (!numericBuffers.ContainsKey(key) || GUI.GetNameOfFocusedControl() != controlName)
                numericBuffers[key] = value.ToString(CultureInfo.InvariantCulture);
            GUI.SetNextControlName(controlName);
            numericBuffers[key] = GUILayout.TextField(numericBuffers[key]);
            if (int.TryParse(numericBuffers[key], NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out int parsed))
            {
                parsed = Mathf.Clamp(parsed, min, max);
                numericBuffers[key] = parsed.ToString(CultureInfo.InvariantCulture);
                return parsed;
            }
            return value;
        }

        private float FloatField(string key, float value, float min, float max)
        {
            string controlName = $"FruitsimFloat_{key}";
            if (!numericBuffers.ContainsKey(key) || GUI.GetNameOfFocusedControl() != controlName)
                numericBuffers[key] = value.ToString("0.###", CultureInfo.InvariantCulture);
            GUI.SetNextControlName(controlName);
            numericBuffers[key] = GUILayout.TextField(numericBuffers[key]);
            if (float.TryParse(numericBuffers[key], NumberStyles.Float,
                    CultureInfo.InvariantCulture, out float parsed))
            {
                parsed = Mathf.Clamp(parsed, min, max);
                return parsed;
            }
            return value;
        }
    }
}

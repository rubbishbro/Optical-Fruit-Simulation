using System;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    [Serializable]
    internal sealed class BlenderPrincipledProfile
    {
        public float[] base_color;
        public float roughness = 0.5f;
        public float metallic;
        public float ior = 1.5f;
        public float transmission;
        public float coat_weight;

        public Color ColorOr(Color fallback)
        {
            if (base_color == null || base_color.Length < 3) return fallback;
            return new Color(base_color[0], base_color[1], base_color[2], 1.0f);
        }
    }

    [Serializable]
    internal sealed class BlenderRigMaterialProfiles
    {
        public BlenderPrincipledProfile detector_glass = new BlenderPrincipledProfile
        {
            base_color = new[] { 0.8f, 0.8f, 0.8f }, roughness = 0.0752688f,
            ior = 1.5f, transmission = 1.0f
        };
        public BlenderPrincipledProfile detector_housing = new BlenderPrincipledProfile
        {
            base_color = new[] { 0.8f, 0.8f, 0.8f }, roughness = 0.35f,
            ior = 1.5f, transmission = 0.0f, coat_weight = 0.1f
        };

        public static BlenderRigMaterialProfiles Load()
        {
            TextAsset asset = Resources.Load<TextAsset>("FruitsimBlenderRigMaterials");
            if (asset == null) return new BlenderRigMaterialProfiles();
            BlenderRigMaterialProfiles profile = JsonUtility.FromJson<BlenderRigMaterialProfiles>(asset.text);
            return profile ?? new BlenderRigMaterialProfiles();
        }
    }
}

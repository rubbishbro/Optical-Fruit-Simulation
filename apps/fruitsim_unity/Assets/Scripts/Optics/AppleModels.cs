using System;
using System.Collections.Generic;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    [Serializable]
    public sealed class AppleGeometryParameters
    {
        // Runtime-active: scale. The remaining fields are metadata-only in P0.
        public float scale = 1.0f;
        public float heightRatio = 1.0f;
        public float crownRatio = 0.08f;
        public float asymmetry = 0.0f;
    }

    [Serializable]
    public sealed class AppleVisualMaterial
    {
        // P1 runtime-active visual controls. They are intentionally independent
        // from ApplePhysicalProperties below.
        // The Blender debug scene is a geometry export source, not the
        // authority for apple appearance. These presentation defaults are a
        // parameterized, opaque skin profile consumed by AppleSkin.shader.
        // Physical/NIR properties remain independent below.
        public Color color = new Color(0.58f, 0.025f, 0.012f, 1.0f);
        public float roughness = 0.46f;
        public float metallic = 0.0f;
        public float specularIORLevel = 0.5f;
        public float ior = 1.45f;
        public float spotDensity = 0.06f;
        public float normalStrength = 0.025f;
        public float skinTransmission = 0.16f;

        public static AppleVisualMaterial LoadBlenderDefaults()
        {
            AppleVisualMaterial fallback = new AppleVisualMaterial();
            TextAsset asset = Resources.Load<TextAsset>("FruitsimAppleVisualProfile");
            if (asset == null) return fallback;
            BlenderPrincipledMaterialSpec spec = JsonUtility.FromJson<BlenderPrincipledMaterialSpec>(asset.text);
            if (spec == null || spec.base_color == null || spec.base_color.Length < 3) return fallback;
            fallback.color = new Color(spec.base_color[0], spec.base_color[1], spec.base_color[2], 1.0f);
            fallback.roughness = spec.roughness;
            fallback.metallic = spec.metallic;
            fallback.specularIORLevel = spec.specular_ior_level;
            fallback.ior = spec.ior;
            fallback.spotDensity = spec.spot_density;
            fallback.normalStrength = spec.normal_strength;
            fallback.skinTransmission = spec.skin_transmission;
            return fallback;
        }
    }

    [Serializable]
    internal sealed class BlenderPrincipledMaterialSpec
    {
        public float[] base_color;
        public float alpha = 1.0f;
        public float roughness = 0.5f;
        public float metallic = 0.0f;
        public float specular_ior_level = 0.5f;
        public float ior = 1.5f;
        public float spot_density = 0.06f;
        public float normal_strength = 0.025f;
        public float skin_transmission = 0.16f;
    }

    [Serializable]
    public sealed class ApplePhysicalProperties
    {
        // Physical properties are tracked for simulation provenance and remain
        // independent from the visible material in the Unity renderer.
        public float sscBrix = 12.5f;
        public float waterContent = 0.74f;
        public float absorptionScale = 1.0f;
        public float reducedScatteringScale = 1.0f;
        public float refractiveIndex = 1.36f;
    }

    [Serializable]
    public sealed class ApplePose
    {
        public Vector3 position = Vector3.zero;
        public Vector3 eulerAngles = Vector3.zero;
    }

    [Serializable]
    public sealed class AppleGenerationRequest
    {
        public int seed = 20260920;
        public AppleGeometryParameters geometry = new AppleGeometryParameters();
        public AppleVisualMaterial visualMaterial = new AppleVisualMaterial();
        public ApplePhysicalProperties physical = new ApplePhysicalProperties();
        public ApplePose pose = new ApplePose();
    }

    [Serializable]
    public sealed class AppleGenerationCapabilities
    {
        public string[] activeGeometryParameters = { "scale" };
        public string[] metadataOnlyGeometryParameters = { "heightRatio", "crownRatio", "asymmetry" };
        public string[] activeVisualParameters =
        {
            "color", "roughness", "metallic", "specularIORLevel", "ior", "spotDensity", "normalStrength", "skinTransmission"
        };
        public string[] metadataOnlyVisualParameters = { };
        public string[] metadataOnlyPhysicalParameters =
        {
            "sscBrix", "waterContent", "absorptionScale", "reducedScatteringScale", "refractiveIndex"
        };
        public string[] activePoseParameters = { "position", "eulerAngles" };
        public bool poseAffectsIdentity = true;
    }

    /// <summary>
    /// Stable handle returned by the generator.  Physical fields are retained
    /// as metadata and are intentionally not used to choose the visual shader.
    /// </summary>
    [Serializable]
    public sealed class AppleInstance
    {
        public string sampleId;
        public int seed;
        public AppleGeometryParameters geometry;
        public AppleVisualMaterial visualMaterial;
        public ApplePhysicalProperties physical;
        public ApplePose pose;
        public GameObject unityObject;
        public GameObject containerObject;

        [NonSerialized] private List<Material> ownedRuntimeMaterials = new List<Material>();

        public string ObjectId => unityObject == null ? string.Empty : unityObject.GetInstanceID().ToString();
        public int OwnedRuntimeMaterialCount => ownedRuntimeMaterials == null ? 0 : ownedRuntimeMaterials.Count;

        internal void TrackOwnedRuntimeMaterial(Material material)
        {
            if (material == null) return;
            if (ownedRuntimeMaterials == null) ownedRuntimeMaterials = new List<Material>();
            ownedRuntimeMaterials.Add(material);
        }

        internal List<Material> ReleaseOwnedRuntimeMaterials()
        {
            List<Material> released = ownedRuntimeMaterials ?? new List<Material>();
            ownedRuntimeMaterials = new List<Material>();
            return released;
        }
    }
}

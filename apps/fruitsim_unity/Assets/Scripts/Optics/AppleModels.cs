using System;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    [Serializable]
    public sealed class AppleGeometryParameters
    {
        public float scale = 1.0f;
        public float heightRatio = 1.0f;
        public float crownRatio = 0.08f;
        public float asymmetry = 0.0f;
    }

    [Serializable]
    public sealed class AppleVisualMaterial
    {
        public Color color = new Color(0.48f, 0.035f, 0.025f, 1.0f);
        public float roughness = 0.68f;
        public float spotDensity = 0.0f;
        public float normalStrength = 0.0f;
    }

    [Serializable]
    public sealed class ApplePhysicalProperties
    {
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

        public string ObjectId => unityObject == null ? string.Empty : unityObject.GetInstanceID().ToString();
    }
}

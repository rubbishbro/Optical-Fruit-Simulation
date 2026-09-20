using System;
using System.Globalization;
using System.Linq;
using Fruitsim.UnityOptics;
using UnityEditor;
using UnityEngine;

public static class AppleCorrectnessChecks
{
    private static int passed;

    public static void RunFromCommandLine()
    {
        passed = 0;
        try
        {
            RunIdentityChecks();
            RunSnapshotAndLifecycleChecks();
            Debug.Log($"FRUITSIM_UNITY_CORRECTNESS passed={passed} failed=0");
            EditorApplication.Exit(0);
        }
        catch (Exception error)
        {
            Debug.LogException(error);
            Debug.LogError($"FRUITSIM_UNITY_CORRECTNESS passed={passed} failed=1");
            EditorApplication.Exit(1);
        }
    }

    private static void RunIdentityChecks()
    {
        AppleGenerationRequest first = CreateRequest();
        AppleGenerationRequest sameValuesDifferentAssignmentOrder = new AppleGenerationRequest();
        sameValuesDifferentAssignmentOrder.pose.eulerAngles = first.pose.eulerAngles;
        sameValuesDifferentAssignmentOrder.physical.refractiveIndex = first.physical.refractiveIndex;
        sameValuesDifferentAssignmentOrder.visualMaterial.color = first.visualMaterial.color;
        sameValuesDifferentAssignmentOrder.geometry.scale = first.geometry.scale;
        sameValuesDifferentAssignmentOrder.seed = first.seed;
        sameValuesDifferentAssignmentOrder.geometry.heightRatio = first.geometry.heightRatio;
        sameValuesDifferentAssignmentOrder.geometry.crownRatio = first.geometry.crownRatio;
        sameValuesDifferentAssignmentOrder.geometry.asymmetry = first.geometry.asymmetry;
        sameValuesDifferentAssignmentOrder.visualMaterial.roughness = first.visualMaterial.roughness;
        sameValuesDifferentAssignmentOrder.visualMaterial.spotDensity = first.visualMaterial.spotDensity;
        sameValuesDifferentAssignmentOrder.visualMaterial.normalStrength = first.visualMaterial.normalStrength;
        sameValuesDifferentAssignmentOrder.physical.sscBrix = first.physical.sscBrix;
        sameValuesDifferentAssignmentOrder.physical.waterContent = first.physical.waterContent;
        sameValuesDifferentAssignmentOrder.physical.absorptionScale = first.physical.absorptionScale;
        sameValuesDifferentAssignmentOrder.physical.reducedScatteringScale = first.physical.reducedScatteringScale;
        sameValuesDifferentAssignmentOrder.pose.position = first.pose.position;

        string baseline = AppleRequestIdentity.CreateSampleId(first);
        Check(baseline == AppleRequestIdentity.CreateSampleId(first), "same request must have stable id");
        Check(baseline == AppleRequestIdentity.CreateSampleId(sameValuesDifferentAssignmentOrder), "assignment order must not affect id");

        CultureInfo originalCulture = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR");
            Check(baseline == AppleRequestIdentity.CreateSampleId(first), "locale must not affect float identity");
        }
        finally
        {
            CultureInfo.CurrentCulture = originalCulture;
        }

        AppleGenerationRequest changed = AppleRequestIdentity.Snapshot(first);
        changed.seed++;
        Check(baseline != AppleRequestIdentity.CreateSampleId(changed), "seed must affect id");
        changed = AppleRequestIdentity.Snapshot(first);
        changed.geometry.heightRatio += 0.01f;
        Check(baseline != AppleRequestIdentity.CreateSampleId(changed), "geometry must affect id");
        changed = AppleRequestIdentity.Snapshot(first);
        changed.physical.waterContent += 0.01f;
        Check(baseline != AppleRequestIdentity.CreateSampleId(changed), "physical parameters must affect id");
        changed = AppleRequestIdentity.Snapshot(first);
        changed.visualMaterial.roughness += 0.01f;
        Check(baseline != AppleRequestIdentity.CreateSampleId(changed), "visual parameters must affect id");
        changed = AppleRequestIdentity.Snapshot(first);
        changed.pose.position.x += 0.01f;
        Check(baseline != AppleRequestIdentity.CreateSampleId(changed), "pose is identity-relevant in P0");
    }

    private static void RunSnapshotAndLifecycleChecks()
    {
        GameObject host = new GameObject("AppleCorrectnessHost");
        try
        {
            AppleGenerator generator = host.AddComponent<AppleGenerator>();
            AppleGenerationRequest request = CreateRequest();
            int baselineMaterials = CountOwnedMaterialNames();
            AppleInstance instance = generator.GenerateApple(request);
            Check(instance.OwnedRuntimeMaterialCount > 0, "generator must track owned runtime materials");
            string sampleId = instance.sampleId;
            float geometrySnapshot = instance.geometry.heightRatio;
            float physicalSnapshot = instance.physical.waterContent;
            float visualSnapshot = instance.visualMaterial.roughness;
            Vector3 poseSnapshot = instance.pose.position;

            request.geometry.heightRatio += 4.0f;
            request.physical.waterContent += 4.0f;
            request.visualMaterial.roughness += 4.0f;
            request.pose.position += Vector3.one * 4.0f;
            Check(instance.geometry.heightRatio == geometrySnapshot, "geometry must be a generation snapshot");
            Check(instance.physical.waterContent == physicalSnapshot, "physical values must be a generation snapshot");
            Check(instance.visualMaterial.roughness == visualSnapshot, "visual values must be a generation snapshot");
            Check(instance.pose.position == poseSnapshot, "pose must be a generation snapshot");
            Check(instance.sampleId == sampleId, "instance id must remain immutable after request mutation");

            generator.DestroyApple(instance);
            Check(CountOwnedMaterialNames() == baselineMaterials, "destroy must release generator-owned materials");

            GameObject sharedSource = Resources.Load<GameObject>("FruitsimBlenderRig");
            Check(sharedSource != null, "shared source asset must remain available");
            for (int index = 0; index < 5; index++)
            {
                AppleInstance repeated = generator.GenerateApple(CreateRequest());
                generator.DestroyApple(repeated);
            }
            Check(CountOwnedMaterialNames() == baselineMaterials, "repeated generate/destroy must not grow material count");
            Check(Resources.Load<GameObject>("FruitsimBlenderRig") == sharedSource, "shared source must not be destroyed");
            Check(generator.Capabilities.metadataOnlyGeometryParameters.Contains("heightRatio"), "capabilities must expose metadata-only geometry fields");
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(host);
        }
    }

    private static AppleGenerationRequest CreateRequest()
    {
        return new AppleGenerationRequest
        {
            seed = 20260920,
            geometry = new AppleGeometryParameters { scale = 1.1f, heightRatio = 0.94f, crownRatio = 0.07f, asymmetry = 0.03f },
            visualMaterial = new AppleVisualMaterial
            {
                color = new Color(0.5f, 0.04f, 0.02f, 1.0f), roughness = 0.61f, spotDensity = 0.02f, normalStrength = 0.1f
            },
            physical = new ApplePhysicalProperties
            {
                sscBrix = 13.2f, waterContent = 0.73f, absorptionScale = 1.02f,
                reducedScatteringScale = 0.98f, refractiveIndex = 1.36f
            },
            pose = new ApplePose { position = new Vector3(0.1f, 0.2f, 0.3f), eulerAngles = new Vector3(2.0f, 8.0f, 1.0f) },
        };
    }

    private static int CountOwnedMaterialNames()
    {
        return Resources.FindObjectsOfTypeAll<Material>().Count(material => material != null && material.name.StartsWith("GeneratedAppleMaterial_"));
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
        passed++;
    }
}

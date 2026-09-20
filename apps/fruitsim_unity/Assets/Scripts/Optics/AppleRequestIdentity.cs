using System;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Pure request snapshot and identity logic. The canonical representation
    /// uses fixed field order and IEEE-754 float bits, so locale and JSON member
    /// ordering cannot change the sample id. Pose is identity-relevant in P0.
    /// </summary>
    public static class AppleRequestIdentity
    {
        public static AppleGenerationRequest Snapshot(AppleGenerationRequest request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            AppleGeometryParameters geometry = request.geometry ?? new AppleGeometryParameters();
            AppleVisualMaterial visual = request.visualMaterial ?? new AppleVisualMaterial();
            ApplePhysicalProperties physical = request.physical ?? new ApplePhysicalProperties();
            ApplePose pose = request.pose ?? new ApplePose();
            return new AppleGenerationRequest
            {
                seed = request.seed,
                geometry = new AppleGeometryParameters
                {
                    scale = geometry.scale,
                    heightRatio = geometry.heightRatio,
                    crownRatio = geometry.crownRatio,
                    asymmetry = geometry.asymmetry,
                },
                visualMaterial = new AppleVisualMaterial
                {
                    color = new Color(visual.color.r, visual.color.g, visual.color.b, visual.color.a),
                    roughness = visual.roughness,
                    spotDensity = visual.spotDensity,
                    normalStrength = visual.normalStrength,
                },
                physical = new ApplePhysicalProperties
                {
                    sscBrix = physical.sscBrix,
                    waterContent = physical.waterContent,
                    absorptionScale = physical.absorptionScale,
                    reducedScatteringScale = physical.reducedScatteringScale,
                    refractiveIndex = physical.refractiveIndex,
                },
                pose = new ApplePose
                {
                    position = new Vector3(pose.position.x, pose.position.y, pose.position.z),
                    eulerAngles = new Vector3(pose.eulerAngles.x, pose.eulerAngles.y, pose.eulerAngles.z),
                },
            };
        }

        public static string Canonicalize(AppleGenerationRequest request)
        {
            AppleGenerationRequest value = Snapshot(request);
            StringBuilder text = new StringBuilder(512);
            Append(text, "schema", "fruitsim.apple-request.v1");
            Append(text, "seed", value.seed.ToString(CultureInfo.InvariantCulture));
            Append(text, "geometry.scale", FloatBits(value.geometry.scale));
            Append(text, "geometry.heightRatio", FloatBits(value.geometry.heightRatio));
            Append(text, "geometry.crownRatio", FloatBits(value.geometry.crownRatio));
            Append(text, "geometry.asymmetry", FloatBits(value.geometry.asymmetry));
            Append(text, "visual.color.r", FloatBits(value.visualMaterial.color.r));
            Append(text, "visual.color.g", FloatBits(value.visualMaterial.color.g));
            Append(text, "visual.color.b", FloatBits(value.visualMaterial.color.b));
            Append(text, "visual.color.a", FloatBits(value.visualMaterial.color.a));
            Append(text, "visual.roughness", FloatBits(value.visualMaterial.roughness));
            Append(text, "visual.spotDensity", FloatBits(value.visualMaterial.spotDensity));
            Append(text, "visual.normalStrength", FloatBits(value.visualMaterial.normalStrength));
            Append(text, "physical.sscBrix", FloatBits(value.physical.sscBrix));
            Append(text, "physical.waterContent", FloatBits(value.physical.waterContent));
            Append(text, "physical.absorptionScale", FloatBits(value.physical.absorptionScale));
            Append(text, "physical.reducedScatteringScale", FloatBits(value.physical.reducedScatteringScale));
            Append(text, "physical.refractiveIndex", FloatBits(value.physical.refractiveIndex));
            Append(text, "pose.position.x", FloatBits(value.pose.position.x));
            Append(text, "pose.position.y", FloatBits(value.pose.position.y));
            Append(text, "pose.position.z", FloatBits(value.pose.position.z));
            Append(text, "pose.eulerAngles.x", FloatBits(value.pose.eulerAngles.x));
            Append(text, "pose.eulerAngles.y", FloatBits(value.pose.eulerAngles.y));
            Append(text, "pose.eulerAngles.z", FloatBits(value.pose.eulerAngles.z));
            return text.ToString();
        }

        public static string CreateSampleId(AppleGenerationRequest request)
        {
            byte[] input = Encoding.UTF8.GetBytes(Canonicalize(request));
            using (SHA256 sha = SHA256.Create())
            {
                byte[] digest = sha.ComputeHash(input);
                StringBuilder hex = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest) hex.Append(value.ToString("x2", CultureInfo.InvariantCulture));
                return "unity-apple-" + hex.ToString();
            }
        }

        private static void Append(StringBuilder text, string name, string value)
        {
            text.Append(name).Append('=').Append(value).Append('\n');
        }

        private static string FloatBits(float value)
        {
            byte[] bytes = BitConverter.GetBytes(value);
            if (BitConverter.IsLittleEndian) Array.Reverse(bytes);
            StringBuilder hex = new StringBuilder(8);
            foreach (byte item in bytes) hex.Append(item.ToString("x2", CultureInfo.InvariantCulture));
            return hex.ToString();
        }
    }
}

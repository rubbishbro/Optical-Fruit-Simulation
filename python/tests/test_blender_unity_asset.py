from __future__ import annotations

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[2]
FBX = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimBlenderRig.fbx"
BOOTSTRAP = ROOT / "apps/fruitsim_unity/Assets/Scripts/Optics/FruitsimOpticsBootstrap.cs"
GENERATOR = ROOT / "apps/fruitsim_unity/Assets/Scripts/Optics/AppleGenerator.cs"
MODELS = ROOT / "apps/fruitsim_unity/Assets/Scripts/Optics/AppleModels.cs"
IDENTITY = ROOT / "apps/fruitsim_unity/Assets/Scripts/Optics/AppleRequestIdentity.cs"
CORRECTNESS = ROOT / "apps/fruitsim_unity/Assets/Editor/AppleCorrectnessChecks.cs"
EXPORTER = ROOT / "scripts/export_blender_ring_rig_to_unity.py"
ORBIT = ROOT / "apps/fruitsim_unity/Assets/Scripts/Optics/OrbitCameraController.cs"
SHADER = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimSolid.shader"
GLASS_SHADER = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimGlass.shader"
RIG_SHADER = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimRig.shader"
APPLE_PROFILE = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimAppleVisualProfile.json"
RIG_MATERIAL_SPEC = ROOT / "apps/fruitsim_unity/Assets/Resources/FruitsimBlenderRigMaterials.json"


class BlenderUnityAssetTests(unittest.TestCase):
    def test_export_contains_complete_authored_instrument(self) -> None:
        self.assertTrue(FBX.is_file(), "Unity Blender rig FBX is missing")
        payload = FBX.read_bytes()
        self.assertGreater(len(payload), 100_000)
        for name in ("BlenderApple", "DetectorGlass", "DetectorHousing"):
            self.assertIn(name.encode(), payload)
        for index in range(12):
            self.assertIn(f"RingLampHousing_{index:02d}".encode(), payload)
            self.assertIn(f"RingLampEmitter_{index:02d}".encode(), payload)

    def test_runtime_requires_blender_rig_without_primitive_fallback(self) -> None:
        source = BOOTSTRAP.read_text(encoding="utf-8")
        generator = GENERATOR.read_text(encoding="utf-8")
        models = MODELS.read_text(encoding="utf-8")
        identity = IDENTITY.read_text(encoding="utf-8")
        self.assertIn("AppleGenerator", source)
        self.assertIn("GenerateApple(", source)
        self.assertIn("Resources.Load<GameObject>(resourcePath)", generator)
        self.assertIn("AppleRequestIdentity.CreateSampleId(snapshot)", generator)
        self.assertIn("SHA256.Create()", identity)
        self.assertIn("FloatBits", identity)
        self.assertIn("AppleRequestIdentity.Snapshot(request)", generator)
        self.assertIn("ReleaseOwnedRuntimeMaterials", generator)
        self.assertIn("ApplePhysicalProperties", models)
        self.assertIn("AppleVisualMaterial", models)
        self.assertNotIn("CreatePrimitive", source)
        self.assertNotIn("Sphere.fbx", source)

    def test_exporter_pins_source_mapping_and_axis_conversion(self) -> None:
        source = EXPORTER.read_text(encoding="utf-8")
        self.assertIn('obj.name == "Apple_ModeB_Debug"', source)
        self.assertIn('axis_forward="-Z"', source)
        self.assertIn('axis_up="Y"', source)
        self.assertIn("PRESENTATION_SCALE = 0.03", source)

    def test_geometry_debug_material_is_not_used_as_apple_authority(self) -> None:
        exporter = EXPORTER.read_text(encoding="utf-8")
        models = MODELS.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        shader = SHADER.read_text(encoding="utf-8")

        self.assertIn("Only", exporter)
        self.assertIn("geometry is authoritative", exporter)
        self.assertNotIn("authored_rgba", exporter)
        self.assertIn('(0.58f, 0.025f, 0.012f, 1.0f)', models)
        self.assertIn('roughness = 0.46f', models)

        # Runtime must preserve the generator-owned apple material after the
        # Blender rig fallback materials are applied to the rest of the rig.
        self.assertIn('renderer.name == "GeneratedApple"', bootstrap)
        self.assertIn('renderer.name == "BlenderApple"', bootstrap)
        self.assertIn('AppleVisualMaterial.LoadBlenderDefaults()', bootstrap)
        self.assertIn('Resources.Load<TextAsset>("FruitsimAppleVisualProfile")', models)

        # The authored ring uses point lights; the shader must account for
        # their world-space position in WebGL instead of treating it as a
        # directional vector.
        self.assertIn('_WorldSpaceLightPos0.w', shader)
        self.assertIn('input.worldPosition', shader)
        self.assertIn('input.vertex.xyz', shader)
        self.assertIn('"RenderType"="Opaque"', shader)
        self.assertIn('ZWrite On', shader)

    def test_parameterized_apple_profile_reaches_runtime_shader(self) -> None:
        profile = json.loads(APPLE_PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["source"], "parameterized-presentation-profile")
        self.assertEqual(profile["alpha"], 1.0)
        self.assertAlmostEqual(profile["roughness"], 0.46, places=4)
        self.assertAlmostEqual(profile["spot_density"], 0.06, places=4)
        self.assertAlmostEqual(profile["normal_strength"], 0.025, places=4)
        self.assertAlmostEqual(profile["skin_transmission"], 0.16, places=4)
        for field in ("_Metallic", "_SpecularIORLevel", "_IOR"):
            self.assertIn(field, SHADER.read_text(encoding="utf-8"))

    def test_detector_glass_uses_authored_blender_principled_parameters(self) -> None:
        self.assertTrue(RIG_MATERIAL_SPEC.is_file())
        spec = json.loads(RIG_MATERIAL_SPEC.read_text(encoding="utf-8"))
        glass = spec["detector_glass"]
        housing = spec["detector_housing"]
        self.assertAlmostEqual(glass["transmission"], 1.0, places=5)
        self.assertAlmostEqual(glass["ior"], 1.5, places=5)
        self.assertAlmostEqual(glass["roughness"], 0.075268805, places=5)
        self.assertAlmostEqual(housing["transmission"], 0.0, places=5)
        self.assertAlmostEqual(housing["coat_weight"], 0.1, places=5)
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('Resources.Load<Shader>("FruitsimGlass")', bootstrap)
        self.assertIn('Resources.Load<Shader>("FruitsimRig")', bootstrap)
        self.assertIn('renderer.name == "DetectorGlass"', bootstrap)
        self.assertIn('_Transmission', GLASS_SHADER.read_text(encoding="utf-8"))
        self.assertIn('ZWrite Off', GLASS_SHADER.read_text(encoding="utf-8"))
        self.assertIn('ZWrite On', RIG_SHADER.read_text(encoding="utf-8"))

    def test_exporter_serializes_detector_material_contract(self) -> None:
        exporter = EXPORTER.read_text(encoding="utf-8")
        for field in ('"transmission"', '"coat_weight"', '"surface_render_method"'):
            self.assertIn(field, exporter)
        self.assertIn('rig_material_specs["detector_glass"]', exporter)
        self.assertIn('rig_material_specs["detector_housing"]', exporter)
        self.assertIn('FruitsimBlenderRigMaterials.json', exporter)

    def test_webgl_camera_has_orbit_zoom_and_reset_entry_points(self) -> None:
        source = ORBIT.read_text(encoding="utf-8")
        self.assertIn("mouse.leftButton.isPressed", source)
        self.assertIn("public void ZoomIn()", source)
        self.assertIn("public void ZoomOut()", source)
        self.assertIn("public void ResetView()", source)
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('camera.gameObject.name = "FruitsimOrbitCamera"', bootstrap)

    def test_unity_correctness_harness_covers_identity_snapshot_and_lifecycle(self) -> None:
        source = CORRECTNESS.read_text(encoding="utf-8")
        for contract in (
            "same request must have stable id",
            "geometry must affect id",
            "physical parameters must affect id",
            "visual parameters must affect id",
            "pose is identity-relevant in P0",
            "geometry must be a generation snapshot",
            "destroy must release generator-owned materials",
            "repeated generate/destroy must not grow material count",
            "shared source must not be destroyed",
        ):
            self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()

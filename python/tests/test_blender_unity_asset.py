from __future__ import annotations

from pathlib import Path
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

# Unity optical rig

The runtime rig supports two modes through `IlluminationMode`:

- `Coaxial`: one source on the apple Y axis and the sensor remains on the same axis.
- `RingIllumination`: uniformly spaced SpotLight preview objects under
  `RingLightRig`, with equal optical power per source and a separate finite
  circular `SensorModel` under `SensorRig`.

`IlluminationRigController.GetOpticalConfiguration()` is the transport-facing
API. It returns source position, direction, power, divergence, and sensor
aperture/FOV without exposing Unity `GameObject` objects to Monte Carlo code.
The visual metal housing and debug rays are not part of this configuration.

The current minimal sample scene creates a controller and IMGUI control panel
automatically at runtime. A real apple generator should call:

```csharp
controller.SetAppleRoot(generatedApple.transform);
```

The controller then recomputes the bounding-box-relative ring and sensor
positions without regenerating the apple.

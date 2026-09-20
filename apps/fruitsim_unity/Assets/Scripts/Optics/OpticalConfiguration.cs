using System;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    public enum IlluminationMode
    {
        Coaxial,
        RingIllumination
    }

    [Serializable]
    public struct PhotonSourceConfiguration
    {
        public Vector3 position;
        public Vector3 direction;
        public float opticalPower;
        public float beamDivergenceDeg;
        public int sourceIndex;
    }

    [Serializable]
    public struct SensorOpticalConfiguration
    {
        public Vector3 center;
        public Vector3 normal;
        public float radius;
        public float fovDeg;
    }

    [Serializable]
    public sealed class OpticalConfiguration
    {
        public IlluminationMode mode;
        public PhotonSourceConfiguration[] sources;
        public SensorOpticalConfiguration sensor;
        public float totalOpticalPower;
        public bool enableHousingReflection;

        public bool IsValid
        {
            get
            {
                return sources != null && sources.Length > 0
                    && sensor.radius > 0.0f && sensor.fovDeg > 0.0f;
            }
        }
    }
}

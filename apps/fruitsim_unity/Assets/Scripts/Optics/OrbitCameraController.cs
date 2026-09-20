using UnityEngine;

#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Fruitsim.UnityOptics
{
    /// <summary>Mouse/touch orbit camera for the WebGL instrument viewer.</summary>
    public sealed class OrbitCameraController : MonoBehaviour
    {
        [SerializeField] private float rotateSensitivity = 0.18f;
        [SerializeField] private float zoomSensitivity = 0.0015f;
        [SerializeField] private float minDistance = 3.0f;
        [SerializeField] private float maxDistance = 14.0f;

        private Vector3 target;
        private float distance;
        private float yaw;
        private float pitch;
        private float initialDistance;
        private float initialYaw;
        private float initialPitch;
        private bool initialized;

        public void Initialize(Vector3 orbitTarget, Vector3 cameraPosition)
        {
            target = orbitTarget;
            Vector3 offset = cameraPosition - target;
            distance = Mathf.Clamp(offset.magnitude, minDistance, maxDistance);
            yaw = Mathf.Atan2(offset.x, -offset.z) * Mathf.Rad2Deg;
            pitch = Mathf.Asin(offset.y / Mathf.Max(distance, 0.001f)) * Mathf.Rad2Deg;
            initialDistance = distance;
            initialYaw = yaw;
            initialPitch = pitch;
            initialized = true;
            ApplyTransform();
        }

        private void Update()
        {
            if (!initialized) return;
#if ENABLE_INPUT_SYSTEM
            Mouse mouse = Mouse.current;
            if (mouse != null)
            {
                if (mouse.leftButton.isPressed)
                {
                    Vector2 delta = mouse.delta.ReadValue();
                    yaw += delta.x * rotateSensitivity;
                    pitch = Mathf.Clamp(pitch - delta.y * rotateSensitivity, -20.0f, 75.0f);
                }
                float scroll = mouse.scroll.ReadValue().y;
                if (Mathf.Abs(scroll) > 0.01f)
                    distance = Mathf.Clamp(distance * Mathf.Exp(-scroll * zoomSensitivity), minDistance, maxDistance);
            }
#endif
#if ENABLE_LEGACY_INPUT_MANAGER
            if (Input.GetMouseButton(0))
            {
                yaw += Input.GetAxis("Mouse X") * rotateSensitivity * 12.0f;
                pitch = Mathf.Clamp(pitch - Input.GetAxis("Mouse Y") * rotateSensitivity * 12.0f, -20.0f, 75.0f);
            }
            float legacyScroll = Input.mouseScrollDelta.y;
            if (Mathf.Abs(legacyScroll) > 0.01f)
                distance = Mathf.Clamp(distance * Mathf.Exp(-legacyScroll * 0.18f), minDistance, maxDistance);
#endif
            ApplyTransform();
        }

        public void ZoomIn() { distance = Mathf.Clamp(distance * 0.82f, minDistance, maxDistance); ApplyTransform(); }
        public void ZoomOut() { distance = Mathf.Clamp(distance * 1.22f, minDistance, maxDistance); ApplyTransform(); }
        public void ResetView()
        {
            distance = initialDistance;
            yaw = initialYaw;
            pitch = initialPitch;
            ApplyTransform();
        }

        private void ApplyTransform()
        {
            float yawRad = yaw * Mathf.Deg2Rad;
            float pitchRad = pitch * Mathf.Deg2Rad;
            float horizontal = distance * Mathf.Cos(pitchRad);
            Vector3 offset = new Vector3(
                horizontal * Mathf.Sin(yawRad),
                distance * Mathf.Sin(pitchRad),
                -horizontal * Mathf.Cos(yawRad));
            transform.position = target + offset;
            transform.LookAt(target, Vector3.up);
        }
    }
}

using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace Fruitsim.WebGL
{
    /// <summary>
    /// Browser WebSocket bridge for the versioned Fruitsim protocol.
    /// The WebGL build never opens a native socket and never runs the C++ worker.
    /// </summary>
    public sealed class FruitsimWebSocketClient : MonoBehaviour
    {
        [SerializeField] private string url = "ws://127.0.0.1:8765";
        [SerializeField] private bool connectOnStart = true;
        private string callbackObjectName;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void FruitsimWebSocketConnect(string objectName, string socketUrl);

        [DllImport("__Internal")]
        private static extern void FruitsimWebSocketSend(string objectName, string message);

        [DllImport("__Internal")]
        private static extern void FruitsimWebSocketDisconnect(string objectName);
#endif

        public event Action<string> MessageReceived;
        public event Action Connected;
        public event Action<string> Error;
        public event Action Closed;

        public string Url { get => url; set => url = value; }

        private void Awake()
        {
            callbackObjectName = $"{gameObject.name}_{GetInstanceID()}";
            gameObject.name = callbackObjectName;
        }

        private void Start()
        {
            if (connectOnStart) Connect();
        }

        private void OnDestroy()
        {
            Disconnect();
        }

        public void Connect()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            FruitsimWebSocketConnect(callbackObjectName, url);
#else
            Debug.Log($"[Fruitsim WebGL] WebSocket bridge is active only in a WebGL player: {url}");
#endif
        }

        public void SendJson(string message)
        {
            if (string.IsNullOrWhiteSpace(message)) return;
#if UNITY_WEBGL && !UNITY_EDITOR
            FruitsimWebSocketSend(callbackObjectName, message);
#else
            Debug.Log($"[Fruitsim WebGL] outgoing message: {message}");
#endif
        }

        public void Disconnect()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            if (!string.IsNullOrWhiteSpace(callbackObjectName))
                FruitsimWebSocketDisconnect(callbackObjectName);
#endif
        }

        // Called by the JavaScript WebGL plugin through Unity SendMessage.
        public void OnWebSocketOpened(string unused)
        {
            Connected?.Invoke();
        }

        public void OnWebSocketMessage(string message)
        {
            MessageReceived?.Invoke(message);
        }

        public void OnWebSocketError(string message)
        {
            Error?.Invoke(message);
            Debug.LogWarning($"[Fruitsim WebGL] {message}");
        }

        public void OnWebSocketClosed(string unused)
        {
            Closed?.Invoke();
        }
    }

    public static class FruitsimWebGLBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void CreateIfMissing()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            if (UnityEngine.Object.FindFirstObjectByType<FruitsimWebSocketClient>() != null) return;
            GameObject root = new GameObject("FruitsimWebSocketClient");
            FruitsimWebSocketClient client = root.AddComponent<FruitsimWebSocketClient>();
            client.Url = DefaultGatewayUrl();
#endif
        }

        private static string DefaultGatewayUrl()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            string page = Application.absoluteURL;
            if (Uri.TryCreate(page, UriKind.Absolute, out Uri pageUri))
            {
                string scheme = pageUri.Scheme == "https" ? "wss" : "ws";
                return $"{scheme}://{pageUri.Host}:8765";
            }
#endif
            return "ws://127.0.0.1:8765";
        }
    }
}

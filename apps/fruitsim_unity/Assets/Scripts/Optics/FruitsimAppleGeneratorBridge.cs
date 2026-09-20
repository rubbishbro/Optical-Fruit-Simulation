using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;

namespace Fruitsim.UnityOptics
{
    /// <summary>
    /// Small, explicit WebGL/UI boundary for the AppleGenerator. The browser
    /// sends only a serialized generation request; the generator remains the
    /// single owner of identity, snapshots, materials and object lifetime.
    /// </summary>
    public sealed class FruitsimAppleGeneratorBridge : MonoBehaviour
    {
        [Serializable]
        private sealed class BatchRequest
        {
            public int count = 1;
            public int base_seed = 20260920;
            public AppleGenerationRequest request = new AppleGenerationRequest();
        }

        [SerializeField] private AppleGenerator generator;
        [SerializeField] private int maxBatchCount = 32;
        private readonly List<AppleInstance> generated = new List<AppleInstance>();

        public string LastSampleId { get; private set; } = string.Empty;
        public int GeneratedCount => generated.Count;

        public void Initialize(AppleGenerator value)
        {
            generator = value;
        }

        public void GenerateAppleJson(string json)
        {
            try
            {
                AppleGenerationRequest request = JsonUtility.FromJson<AppleGenerationRequest>(json);
                if (request == null) throw new ArgumentException("apple request JSON is empty");
                AppleInstance instance = GetGenerator().GenerateApple(request);
                generated.Add(instance);
                LastSampleId = instance.sampleId;
                Debug.Log($"[Fruitsim Apple] generated sample_id={instance.sampleId}");
                NotifyBrowser("FruitsimAppleGenerated", instance.sampleId);
            }
            catch (Exception error)
            {
                Debug.LogError($"[Fruitsim Apple] generate failed: {error.Message}");
                NotifyBrowser("FruitsimAppleGenerationFailed", error.Message);
            }
        }

        public void GenerateBatchJson(string json)
        {
            try
            {
                BatchRequest batch = JsonUtility.FromJson<BatchRequest>(json);
                if (batch == null) throw new ArgumentException("batch request JSON is empty");
                int count = Mathf.Clamp(batch.count, 1, maxBatchCount);
                AppleGenerationRequest template = batch.request ?? new AppleGenerationRequest();
                List<string> ids = new List<string>(count);
                for (int index = 0; index < count; index++)
                {
                    AppleGenerationRequest request = AppleRequestIdentity.Snapshot(template);
                    request.seed = batch.base_seed + index;
                    AppleInstance instance = GetGenerator().GenerateApple(request);
                    generated.Add(instance);
                    ids.Add(instance.sampleId);
                }
                LastSampleId = ids[ids.Count - 1];
                string joined = string.Join(",", ids.ToArray());
                Debug.Log($"[Fruitsim Apple] generated batch count={ids.Count} sample_ids={joined}");
                NotifyBrowser("FruitsimAppleBatchGenerated", joined);
            }
            catch (Exception error)
            {
                Debug.LogError($"[Fruitsim Apple] batch failed: {error.Message}");
                NotifyBrowser("FruitsimAppleGenerationFailed", error.Message);
            }
        }

        public void ClearGenerated()
        {
            for (int index = generated.Count - 1; index >= 0; index--)
                GetGenerator().DestroyApple(generated[index]);
            generated.Clear();
            LastSampleId = string.Empty;
            NotifyBrowser("FruitsimAppleCleared", string.Empty);
        }

        private AppleGenerator GetGenerator()
        {
            if (generator == null) generator = GetComponent<AppleGenerator>();
            if (generator == null) throw new MissingReferenceException("AppleGenerator is not attached to the experiment root.");
            return generator;
        }

        private static void NotifyBrowser(string callback, string value)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            FruitsimAppleNotify(callback, value ?? string.Empty);
#endif
        }

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void FruitsimAppleNotify(string callbackName, string value);
#endif
    }
}

using System;
using System.IO;
using DiagnosticsProcess = System.Diagnostics.Process;
using UnityEngine;
using UnityEngine.Profiling;

namespace Fruitsim.RunViewer
{
    public enum RunViewerState
    {
        Empty,
        Ready,
        RecoverableError,
        BlockingError
    }

    /// <summary>
    /// Always-available development panel for inspecting the current Run.
    /// It watches status.json so a separately running pipeline can be observed.
    /// </summary>
    public sealed class FruitsimRunDebugPanel : MonoBehaviour
    {
        [SerializeField] private string runDirectory = "";
        [SerializeField] private bool visible = true;
        [SerializeField] private float pollSeconds = 0.5f;
        private RunSnapshot snapshot;
        private RunStatusStamp statusStamp;
        private bool hasStatusStamp;
        private string lastError = "No Run loaded. Start a pipeline or choose a Run directory.";
        private RunViewerState viewerState = RunViewerState.Empty;
        private float nextPoll;
        private int statusProbeCount;
        private int loadCount;
        private float metricNextSample;
        private float metricFrameAccumulator;
        private int metricFrameCount;
        private float framesPerSecond;
        private float cpuPercent;
        private long residentBytes;
        private long managedBytes;
        private long allocatedBytes;
        private long monoBytes;
        private int objectCount;
        private double previousCpuSeconds;
        private float previousMetricTime;

        public string RunDirectory { get => runDirectory; set => runDirectory = value; }
        public RunSnapshot Snapshot => snapshot;
        public RunViewerState State => viewerState;
        public int StatusProbeCount => statusProbeCount;
        public int LoadCount => loadCount;

        private void Start()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            visible = false;
            enabled = false;
            return;
#endif
            if (string.IsNullOrWhiteSpace(runDirectory))
                runDirectory = DefaultRunDirectory();
            LoadRun();
        }

        private void Update()
        {
            float now = Time.unscaledTime;
            metricFrameAccumulator += Time.unscaledDeltaTime;
            metricFrameCount++;
            if (now >= nextPoll)
            {
                nextPoll = now + Mathf.Max(0.1f, pollSeconds);
                ProbeRunStatus();
            }
            if (now >= metricNextSample)
            {
                metricNextSample = now + 1.0f;
                SampleRuntimeMetrics();
            }
        }

        public bool LoadRun()
        {
            return LoadRun(true);
        }

        private bool LoadRun(bool report)
        {
            if (!RunArtifactLoader.TryLoad(runDirectory, out RunSnapshot loaded, out string error))
            {
                snapshot = null;
                hasStatusStamp = false;
                lastError = error;
                SetState(ClassifyError(error), error, report);
                return false;
            }
            snapshot = loaded;
            statusStamp = new RunStatusStamp(loaded.statusWriteTimeUtc, loaded.statusFileLength);
            hasStatusStamp = true;
            lastError = string.Empty;
            loadCount++;
            SetState(RunViewerState.Ready, string.Empty, false);
            return true;
        }

        private void ProbeRunStatus()
        {
            statusProbeCount++;
            if (!RunArtifactLoader.TryGetStatusStamp(runDirectory, out RunStatusStamp nextStamp, out string error))
            {
                snapshot = null;
                hasStatusStamp = false;
                lastError = error;
                SetState(ClassifyError(error), error, false);
                return;
            }

            if (snapshot == null || !hasStatusStamp || !nextStamp.Equals(statusStamp))
                LoadRun(false);
        }

        private void SetState(RunViewerState nextState, string message, bool report)
        {
            bool changed = viewerState != nextState || !string.Equals(lastError, message, StringComparison.Ordinal);
            viewerState = nextState;
            if (!changed || !report) return;
            if (nextState == RunViewerState.BlockingError)
                Debug.LogError($"[Fruitsim RunViewer] {message}");
            else if (nextState == RunViewerState.RecoverableError)
                Debug.LogWarning($"[Fruitsim RunViewer] {message}");
        }

        private static RunViewerState ClassifyError(string error)
        {
            if (string.IsNullOrEmpty(error) || error.StartsWith("Run directory", StringComparison.Ordinal) || error.StartsWith("Run is waiting", StringComparison.Ordinal))
                return RunViewerState.Empty;
            if (error.StartsWith("Unsupported Run schema", StringComparison.Ordinal) || error.StartsWith("manifest.run_id", StringComparison.Ordinal) || error.StartsWith("Run contract contains", StringComparison.Ordinal))
                return RunViewerState.BlockingError;
            return RunViewerState.RecoverableError;
        }

        private void SampleRuntimeMetrics()
        {
            framesPerSecond = metricFrameAccumulator > 0.0f ? metricFrameCount / metricFrameAccumulator : 0.0f;
            metricFrameAccumulator = 0.0f;
            metricFrameCount = 0;
            managedBytes = GC.GetTotalMemory(false);
            allocatedBytes = Profiler.GetTotalAllocatedMemoryLong();
            monoBytes = Profiler.GetMonoUsedSizeLong();
            objectCount = UnityEngine.Object.FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Include, FindObjectsSortMode.None).Length;
#if !UNITY_WEBGL
            try
            {
                using (DiagnosticsProcess process = DiagnosticsProcess.GetCurrentProcess())
                {
                    double currentCpuSeconds = process.TotalProcessorTime.TotalSeconds;
                    float elapsed = previousMetricTime > 0.0f ? Mathf.Max(0.001f, Time.unscaledTime - previousMetricTime) : 0.0f;
                    if (elapsed > 0.0f)
                        cpuPercent = (float)Math.Max(0.0, (currentCpuSeconds - previousCpuSeconds) / elapsed / Math.Max(1, Environment.ProcessorCount) * 100.0);
                    previousCpuSeconds = currentCpuSeconds;
                }
                residentBytes = ReadResidentBytes();
            }
            catch (Exception)
            {
                cpuPercent = 0.0f;
                residentBytes = 0;
            }
#endif
            previousMetricTime = Time.unscaledTime;
        }

#if !UNITY_WEBGL
        private static long ReadResidentBytes()
        {
            const string statusPath = "/proc/self/status";
            if (!File.Exists(statusPath)) return 0;
            foreach (string line in File.ReadLines(statusPath))
            {
                if (!line.StartsWith("VmRSS:", StringComparison.Ordinal)) continue;
                string[] fields = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                if (fields.Length >= 2 && long.TryParse(fields[1], out long kilobytes)) return kilobytes * 1024L;
            }
            return 0;
        }
#endif

        private static string FormatBytes(long bytes)
        {
            if (bytes <= 0) return "n/a";
            if (bytes >= 1024L * 1024L) return $"{bytes / 1024.0 / 1024.0:0.0} MiB";
            return $"{bytes / 1024.0:0.0} KiB";
        }

        private void OnGUI()
        {
            if (!visible)
            {
                if (GUI.Button(new Rect(126.0f, 18.0f, 120.0f, 28.0f), "Show Run debug")) visible = true;
                return;
            }
            GUILayout.BeginArea(new Rect(18.0f, 18.0f, 520.0f, 300.0f), GUI.skin.box);
            GUILayout.Label("Fruitsim Run Debug", GUI.skin.GetStyle("boldLabel"));
            GUILayout.BeginHorizontal();
            GUILayout.Label("Run directory", GUILayout.Width(100.0f));
            runDirectory = GUILayout.TextField(runDirectory ?? string.Empty);
            if (GUILayout.Button("Load", GUILayout.Width(60.0f))) LoadRun();
            GUILayout.EndHorizontal();
            if (snapshot == null)
            {
                GUILayout.Label($"State: {viewerState}", GUI.skin.GetStyle("boldLabel"));
                GUILayout.Label(lastError, GUI.skin.GetStyle("label"));
                GUILayout.Label("Empty state: waiting for a valid Run contract.", GUI.skin.GetStyle("label"));
            }
            else
            {
                GUILayout.Label($"State: {viewerState}", GUI.skin.GetStyle("boldLabel"));
                GUILayout.Label($"ID: {snapshot.manifest.run_id}");
                GUILayout.Label($"State: {snapshot.status.state}  Stage: {snapshot.status.stage ?? "-"}");
                GUILayout.Label($"Source: {snapshot.manifest.source_type}  Seed: {snapshot.manifest.seed}");
                GUILayout.Label($"Samples: {snapshot.sampleRows}  Spectral rows: {snapshot.spectralRows}");
                GUILayout.Label($"Artifacts: {(snapshot.artifacts.artifacts == null ? 0 : snapshot.artifacts.artifacts.Length)}");
                GUILayout.Label($"Model: {snapshot.manifest.model_status}  Backend: {snapshot.manifest.backend}");
                if (snapshot.manifest.warnings != null)
                    foreach (string warning in snapshot.manifest.warnings)
                        GUILayout.Label($"Warning: {warning}", GUI.skin.GetStyle("warningLabel"));
            }
            GUILayout.Label($"Polling: {pollSeconds:0.0}s  probes: {statusProbeCount}  loads: {loadCount}");
            GUILayout.Label($"Runtime: {framesPerSecond:0.0} FPS  CPU: {cpuPercent:0.0}%  Objects: {objectCount}");
            GUILayout.Label($"Memory: RSS {FormatBytes(residentBytes)}  GC {FormatBytes(managedBytes)}  Unity {FormatBytes(allocatedBytes)}  Mono {FormatBytes(monoBytes)}");
            if (GUILayout.Button(visible ? "Hide debug panel" : "Show debug panel")) visible = !visible;
            GUILayout.EndArea();
        }

        private static string DefaultRunDirectory()
        {
            string environmentPath = Environment.GetEnvironmentVariable("FRUITSIM_RUN_DIR");
            if (!string.IsNullOrWhiteSpace(environmentPath)) return Path.GetFullPath(environmentPath);

            string[] arguments = Environment.GetCommandLineArgs();
            for (int i = 0; i + 1 < arguments.Length; i++)
            {
                if (string.Equals(arguments[i], "-fruitsim-run", StringComparison.OrdinalIgnoreCase))
                    return Path.GetFullPath(arguments[i + 1]);
            }

            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            return Path.Combine(projectRoot, "results", "runs", "wp3_math_demo_seed20260919");
        }
    }

    public static class FruitsimRunDebugBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void CreateIfMissing()
        {
            if (UnityEngine.Object.FindFirstObjectByType<FruitsimRunDebugPanel>() != null) return;
            GameObject root = new GameObject("FruitsimRunDebugPanel");
            root.AddComponent<FruitsimRunDebugPanel>();
        }
    }
}

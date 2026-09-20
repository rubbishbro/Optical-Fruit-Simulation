#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;

namespace Fruitsim.Editor
{
    public static class FruitsimBuild
    {
        private static bool IsDevelopmentBuild()
        {
            string value = Environment.GetEnvironmentVariable("FRUITSIM_BUILD_MODE");
            return string.Equals(value, "development", StringComparison.OrdinalIgnoreCase)
                || string.Equals(value, "debug", StringComparison.OrdinalIgnoreCase);
        }

        private static BuildOptions BuildOptionsForTarget(bool supportsProfiler)
        {
            if (!IsDevelopmentBuild()) return BuildOptions.None;
            BuildOptions options = BuildOptions.Development | BuildOptions.AllowDebugging;
            if (supportsProfiler) options |= BuildOptions.ConnectWithProfiler;
            return options;
        }

        public static void BuildLinux()
        {
            string scenePath = "Assets/Scenes/SampleScene.unity";
            ConfigureScenes(scenePath);
            string projectRoot = Directory.GetParent(UnityEngine.Application.dataPath).FullName;
            string outputPath = Environment.GetEnvironmentVariable("FRUITSIM_BUILD_OUTPUT");
            if (string.IsNullOrEmpty(outputPath))
                outputPath = Path.Combine(projectRoot, "build", "Fruitsim.x86_64");
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath));
            BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { scenePath },
                locationPathName = outputPath,
                target = BuildTarget.StandaloneLinux64,
                options = BuildOptionsForTarget(true)
            });
            if (report.summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"Fruitsim Linux build failed: {report.summary.result}");
            UnityEngine.Debug.Log($"Fruitsim Linux build completed: {outputPath}");
        }

        public static void BuildWebGL()
        {
            string scenePath = "Assets/Scenes/SampleScene.unity";
            ConfigureScenes(scenePath);
            string projectRoot = Directory.GetParent(UnityEngine.Application.dataPath).FullName;
            string outputPath = Environment.GetEnvironmentVariable("FRUITSIM_BUILD_OUTPUT");
            if (string.IsNullOrEmpty(outputPath))
                outputPath = Path.Combine(projectRoot, "build", "WebGL");
            Directory.CreateDirectory(outputPath);
            BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { scenePath },
                locationPathName = outputPath,
                target = BuildTarget.WebGL,
                options = BuildOptionsForTarget(false)
            });
            if (report.summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"Fruitsim WebGL build failed: {report.summary.result}");
            UnityEngine.Debug.Log($"Fruitsim WebGL build completed: {outputPath}");
        }

        private static void ConfigureScenes(string scenePath)
        {
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
        }
    }
}
#endif

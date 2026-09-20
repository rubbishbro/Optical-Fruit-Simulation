using System;
using System.IO;
using UnityEngine;

namespace Fruitsim.RunViewer
{
    public sealed class RunSnapshot
    {
        public string directory;
        public RunManifest manifest;
        public RunStatus status;
        public RunArtifactIndex artifacts;
        public int sampleRows;
        public int spectralRows;
        public DateTime statusWriteTimeUtc;
        public long statusFileLength;
    }

    public readonly struct RunStatusStamp : IEquatable<RunStatusStamp>
    {
        public readonly DateTime writeTimeUtc;
        public readonly long length;

        public RunStatusStamp(DateTime writeTimeUtc, long length)
        {
            this.writeTimeUtc = writeTimeUtc;
            this.length = length;
        }

        public bool Equals(RunStatusStamp other)
        {
            return writeTimeUtc == other.writeTimeUtc && length == other.length;
        }

        public override bool Equals(object obj)
        {
            return obj is RunStatusStamp other && Equals(other);
        }

        public override int GetHashCode()
        {
            unchecked
            {
                return (writeTimeUtc.GetHashCode() * 397) ^ length.GetHashCode();
            }
        }
    }

    /// <summary>
    /// File-only reader for the versioned Run contract. It never mutates a Run
    /// and keeps Unity independent from Python or the C++ process.
    /// </summary>
    public static class RunArtifactLoader
    {
        public static bool TryLoad(string directory, out RunSnapshot snapshot, out string error)
        {
            snapshot = null;
            error = string.Empty;
            if (string.IsNullOrWhiteSpace(directory))
            {
                error = "Run directory is empty.";
                return false;
            }

            string root = Path.GetFullPath(directory);
            if (!Directory.Exists(root))
            {
                error = $"Run directory does not exist: {root}";
                return false;
            }

            try
            {
                RunManifest manifest = ReadJson<RunManifest>(Path.Combine(root, "manifest.json"));
                RunStatus status = ReadJson<RunStatus>(Path.Combine(root, "status.json"));
                RunArtifactIndex artifacts = ReadJson<RunArtifactIndex>(Path.Combine(root, "artifacts.json"));
                if (manifest == null || status == null || artifacts == null)
                {
                    error = "Run contract contains an empty JSON document.";
                    return false;
                }
                if (manifest.schema_version != 1 || status.schema_version != 1 || artifacts.schema_version != 1)
                {
                    error = "Unsupported Run schema version; expected v1.";
                    return false;
                }
                if (string.IsNullOrEmpty(manifest.run_id) || manifest.run_id != status.run_id)
                {
                    error = "manifest.run_id and status.run_id do not match.";
                    return false;
                }
                snapshot = new RunSnapshot
                {
                    directory = root,
                    manifest = manifest,
                    status = status,
                    artifacts = artifacts,
                    sampleRows = CountDataRows(Path.Combine(root, "data", "samples.csv")),
                    spectralRows = CountDataRows(Path.Combine(root, "data", "spectra.csv")),
                    statusWriteTimeUtc = File.GetLastWriteTimeUtc(Path.Combine(root, "status.json")),
                    statusFileLength = new FileInfo(Path.Combine(root, "status.json")).Length
                };
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is UnauthorizedAccessException || exception is ArgumentException)
            {
                error = exception.Message;
                return false;
            }
            catch (Exception exception)
            {
                error = $"Run contract could not be read: {exception.Message}";
                return false;
            }
        }

        public static bool TryGetStatusStamp(string directory, out RunStatusStamp stamp, out string error)
        {
            stamp = default;
            error = string.Empty;
            if (string.IsNullOrWhiteSpace(directory))
            {
                error = "Run directory is empty.";
                return false;
            }

            string root = Path.GetFullPath(directory);
            if (!Directory.Exists(root))
            {
                error = $"Run directory does not exist: {root}";
                return false;
            }

            try
            {
                string statusPath = Path.Combine(root, "status.json");
                if (!File.Exists(statusPath))
                {
                    error = "Run is waiting for status.json.";
                    return false;
                }

                FileInfo info = new FileInfo(statusPath);
                stamp = new RunStatusStamp(info.LastWriteTimeUtc, info.Length);
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is UnauthorizedAccessException || exception is ArgumentException)
            {
                error = exception.Message;
                return false;
            }
        }

        private static T ReadJson<T>(string path) where T : class
        {
            if (!File.Exists(path)) throw new FileNotFoundException("Missing Run contract file", path);
            return JsonUtility.FromJson<T>(File.ReadAllText(path));
        }

        private static int CountDataRows(string path)
        {
            if (!File.Exists(path)) return 0;
            int rows = 0;
            using (StreamReader reader = new StreamReader(path))
            {
                if (reader.ReadLine() == null) return 0;
                while (reader.ReadLine() != null) rows++;
            }
            return rows;
        }
    }
}

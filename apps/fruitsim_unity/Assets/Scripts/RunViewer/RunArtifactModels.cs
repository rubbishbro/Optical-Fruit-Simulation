using System;

namespace Fruitsim.RunViewer
{
    [Serializable]
    public sealed class RunCoordinateSystem
    {
        public string name;
        public string handedness;
        public string up_axis;
        public string length_unit;
        public float[] world_to_unity;
    }

    [Serializable]
    public sealed class RunManifest
    {
        public int schema_version;
        public string run_id;
        public string parent_run_id;
        public string created_at;
        public string status;
        public string source_type;
        public string generator_version;
        public string configuration_hash;
        public int seed;
        public string git_commit;
        public string backend;
        public RunCoordinateSystem coordinate_system;
        public string data_status;
        public string model_status;
        public string[] warnings;
        public string artifacts_index;
        public string[] notes;
    }

    [Serializable]
    public sealed class RunStatus
    {
        public int schema_version;
        public string run_id;
        public string state;
        public string updated_at;
        public int completed;
        public int total;
        public string stage;
        public string message;
        public string error_code;
    }

    [Serializable]
    public sealed class RunArtifact
    {
        public string artifact_id;
        public string role;
        public string relative_path;
        public string media_type;
        public int schema_version;
        public string producer;
        public string unit;
        public int[] shape;
        public string dtype;
        public string sha256;
    }

    [Serializable]
    public sealed class RunArtifactIndex
    {
        public int schema_version;
        public RunArtifact[] artifacts;
    }
}

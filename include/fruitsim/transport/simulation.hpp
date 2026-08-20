#pragma once

#include "fruitsim/geometry/layered_sphere.hpp"
#include "fruitsim/optics/optics.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace fruitsim {

struct PencilBeamSource {
    std::string type = "pencil";
    Vec3 position_mm{};
    Vec3 direction{0.0, 0.0, 1.0};
    double gaussian_sigma_mm = 0.0;
};

struct SpectralMedium {
    double wavelength_nm = 0.0;
    std::vector<OpticalProperties> regions;
};

struct ScoringOptions {
    std::size_t radial_bins = 32;
    double radial_max_mm = 40.0;
    std::size_t grid_size = 0;
    std::size_t depth_bins = 64;
    std::size_t trajectory_limit = 0;
};

struct ExecutionOptions {
    std::uint64_t photons_per_wavelength = 10000;
    std::uint64_t seed = 20260819;
    std::size_t threads = 0;
    std::size_t batch_size = 1024;
    std::size_t max_reduction_batches = 256;
    std::uint32_t max_events = 100000;
    double roulette_threshold = 1.0e-4;
    double roulette_survival = 0.1;
    double boundary_epsilon_mm = 1.0e-7;
    std::string backend = "cpu";
};

struct SimulationMetadata {
    std::string session_id = "fruitsim";
    std::string cultivar = "unknown";
    std::string dataset_id = "unknown";
    std::string source_type = "unknown";
    std::string transport_mode = "scalar";
    std::vector<std::string> assumptions;
};

struct SimulationProblem {
    LayeredSphere domain;
    double exterior_refractive_index = 1.0;
    PencilBeamSource source;
    std::vector<SpectralMedium> spectra;
    ScoringOptions scoring;
    ExecutionOptions execution;
    SimulationMetadata metadata;

    explicit SimulationProblem(LayeredSphere domain_value)
        : domain(std::move(domain_value))
    {
    }

    void validate() const;
};

struct PhotonState {
    Vec3 position_mm{};
    Vec3 direction{0.0, 0.0, 1.0};
    double weight = 1.0;
    int region = kExteriorRegion;
    std::size_t wavelength_index = 0;
    std::uint64_t photon_id = 0;
    std::uint32_t event_count = 0;
};

struct TrajectoryPoint {
    std::uint64_t photon_id = 0;
    std::uint32_t event = 0;
    Vec3 position_mm{};
    double weight = 0.0;
    int region = kExteriorRegion;
};

struct WavelengthResult {
    double wavelength_nm = 0.0;
    std::uint64_t photons = 0;
    double reflectance = 0.0;
    double transmittance = 0.0;
    std::vector<double> absorbed_by_region;
    double discarded_weight = 0.0;
    double energy_residual = 0.0;
    double reflectance_standard_error = 0.0;
    double transmittance_standard_error = 0.0;
    std::vector<double> radial_reflectance;
    std::vector<double> absorption_grid;
    double penetration_q50_mm = 0.0;
    double penetration_q90_mm = 0.0;
    std::vector<TrajectoryPoint> trajectories;
};

struct SimulationResult {
    std::string backend;
    double elapsed_seconds = 0.0;
    std::vector<WavelengthResult> wavelengths;
};

struct ProgressUpdate {
    std::size_t wavelength_index = 0;
    std::uint64_t completed_photons = 0;
    std::uint64_t total_photons = 0;
};

using ProgressSink = std::function<void(const ProgressUpdate&)>;

class ITransportBackend {
public:
    virtual ~ITransportBackend() = default;
    virtual SimulationResult run(
        const SimulationProblem& problem, const ProgressSink& progress = {},
        const std::atomic_bool* cancel = nullptr) const = 0;
    [[nodiscard]] virtual std::string name() const = 0;
};

} // namespace fruitsim

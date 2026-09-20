#pragma once

#include "fruitsim/transport/simulation.hpp"
#include "fruitsim/random.hpp"

#include <cstdint>

namespace fruitsim {

struct BatchResult {
    std::uint64_t photon_count = 0;
    double reflected = 0.0;
    double transmitted = 0.0;
    std::vector<double> absorbed;
    double discarded = 0.0;
    std::uint64_t boundary_failures = 0;
    std::uint64_t max_event_terminations = 0;
    std::vector<double> radial_reflectance;
    std::vector<double> absorption_grid;
    std::vector<std::uint64_t> depth_histogram;
    std::uint64_t detected_photon_count = 0;
    double detected_weight = 0.0;
    double detected_specular_weight = 0.0;
    double detected_diffuse_weight = 0.0;
    double detected_depth_weighted_sum = 0.0;
    double detected_total_path_weighted_sum = 0.0;
    std::vector<double> detected_path_weighted_sum_by_region;
    double detected_zero_depth_weight = 0.0;
    std::vector<double> detected_depth_histogram;
    std::vector<TrajectoryPoint> trajectories;
    std::vector<std::vector<TrajectoryPoint>> detector_trajectories;
};

struct SourceLaunch {
    Vec3 position_mm{};
    Vec3 direction{0.0, 0.0, 1.0};
};

// Public for deterministic source-geometry tests and future instrument tools.
[[nodiscard]] SourceLaunch sample_source_launch(
    const PhotonSource& source, CounterRng& rng);

// Tests the ray after it has escaped into the exterior medium. The detector
// axis points toward the sample, so accepted rays travel within the cone
// around -axis.
[[nodiscard]] bool detector_accepts(
    const CircularDetector& detector, const Vec3& escape_position_mm,
    const Vec3& exterior_direction, double epsilon_mm = 1.0e-9);

// Detector NA is defined in the exterior medium: NA = n_exterior*sin(theta).
[[nodiscard]] double detector_acceptance_half_angle_degrees(
    double numerical_aperture, double exterior_refractive_index);

[[nodiscard]] BatchResult simulate_batch(
    const SimulationProblem& problem, std::size_t wavelength_index,
    std::uint64_t first_photon, std::uint64_t photon_count);

} // namespace fruitsim

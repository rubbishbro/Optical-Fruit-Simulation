#pragma once

#include "fruitsim/transport/simulation.hpp"

#include <cstdint>

namespace fruitsim {

struct BatchResult {
    std::uint64_t photon_count = 0;
    double reflected = 0.0;
    double transmitted = 0.0;
    std::vector<double> absorbed;
    double discarded = 0.0;
    std::vector<double> radial_reflectance;
    std::vector<double> absorption_grid;
    std::vector<std::uint64_t> depth_histogram;
    std::vector<TrajectoryPoint> trajectories;
};

[[nodiscard]] BatchResult simulate_batch(
    const SimulationProblem& problem, std::size_t wavelength_index,
    std::uint64_t first_photon, std::uint64_t photon_count);

} // namespace fruitsim

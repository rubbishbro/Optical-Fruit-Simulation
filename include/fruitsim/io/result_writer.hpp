#pragma once

#include "fruitsim/transport/simulation.hpp"

#include <filesystem>

namespace fruitsim {

void write_simulation_results(
    const SimulationProblem& problem, const SimulationResult& result,
    const std::filesystem::path& output_directory);

} // namespace fruitsim

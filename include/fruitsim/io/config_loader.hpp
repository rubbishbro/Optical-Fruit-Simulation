#pragma once

#include "fruitsim/transport/simulation.hpp"

#include <filesystem>

namespace fruitsim {

[[nodiscard]] SimulationProblem load_simulation_config(const std::filesystem::path& path);
void validate_simulation_config(const std::filesystem::path& path);

} // namespace fruitsim

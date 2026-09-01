#pragma once

#include "fruitsim/geometry/statistical_fuji_shape.hpp"

#include <filesystem>

namespace fruitsim {

[[nodiscard]] StatisticalFujiShape load_statistical_fuji_shape(
    const std::filesystem::path& path);

} // namespace fruitsim

#pragma once

#include "fruitsim/vec3.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fruitsim {

struct StatisticalShapeMode {
    double eigenvalue_mm2 = 0.0;
    double explained_variance_ratio = 0.0;
    // One-standard-deviation radial deformation on the common direction grid.
    std::vector<double> deformation_mm;
};

struct StatisticalShapeMesh {
    std::vector<Vec3> vertices_mm;
    std::vector<std::array<std::size_t, 3>> faces;
    std::vector<double> coefficients_sigma;
};

class StatisticalFujiShape {
public:
    StatisticalFujiShape(
        std::vector<Vec3> directions,
        std::vector<double> mean_radius_mm,
        std::vector<StatisticalShapeMode> modes,
        std::vector<std::array<std::size_t, 3>> faces,
        std::string cultivar_status,
        std::string source_doi);

    [[nodiscard]] const std::vector<Vec3>& directions() const { return directions_; }
    [[nodiscard]] const std::vector<double>& mean_radius_mm() const { return mean_radius_mm_; }
    [[nodiscard]] const std::vector<StatisticalShapeMode>& modes() const { return modes_; }
    [[nodiscard]] const std::vector<std::array<std::size_t, 3>>& faces() const { return faces_; }
    [[nodiscard]] const std::string& cultivar_status() const { return cultivar_status_; }
    [[nodiscard]] const std::string& source_doi() const { return source_doi_; }

    [[nodiscard]] StatisticalShapeMesh mean_shape() const;
    [[nodiscard]] StatisticalShapeMesh sample(
        const std::vector<double>& coefficients_sigma, double sigma_clip = 3.0) const;
    [[nodiscard]] StatisticalShapeMesh sample_random(
        std::uint64_t seed, std::uint64_t sample_id,
        std::size_t active_modes = 0, double sigma_clip = 3.0) const;

private:
    void validate() const;

    std::vector<Vec3> directions_;
    std::vector<double> mean_radius_mm_;
    std::vector<StatisticalShapeMode> modes_;
    std::vector<std::array<std::size_t, 3>> faces_;
    std::string cultivar_status_;
    std::string source_doi_;
};

} // namespace fruitsim

#include "fruitsim/geometry/statistical_fuji_shape.hpp"

#include "fruitsim/random.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace fruitsim {

namespace {

constexpr double kPi = 3.14159265358979323846;

} // namespace

StatisticalFujiShape::StatisticalFujiShape(
    std::vector<Vec3> directions,
    std::vector<double> mean_radius_mm,
    std::vector<StatisticalShapeMode> modes,
    std::vector<std::array<std::size_t, 3>> faces,
    std::string cultivar_status,
    std::string source_doi)
    : directions_(std::move(directions)),
      mean_radius_mm_(std::move(mean_radius_mm)),
      modes_(std::move(modes)),
      faces_(std::move(faces)),
      cultivar_status_(std::move(cultivar_status)),
      source_doi_(std::move(source_doi))
{
    validate();
}

void StatisticalFujiShape::validate() const
{
    if (directions_.size() < 4 || mean_radius_mm_.size() != directions_.size()
        || cultivar_status_.empty() || source_doi_.empty()) {
        throw std::invalid_argument("Invalid StatisticalFujiShape dimensions or provenance");
    }
    for (std::size_t index = 0; index < directions_.size(); ++index) {
        if (std::abs(directions_[index].norm() - 1.0) > 1.0e-7
            || !std::isfinite(mean_radius_mm_[index]) || mean_radius_mm_[index] <= 0.0) {
            throw std::invalid_argument("Shape directions must be unit length and mean radii positive");
        }
    }
    for (const auto& mode : modes_) {
        if (mode.deformation_mm.size() != directions_.size()
            || mode.eigenvalue_mm2 < 0.0 || mode.explained_variance_ratio < 0.0) {
            throw std::invalid_argument("Invalid PCA deformation mode");
        }
        for (const double value : mode.deformation_mm) {
            if (!std::isfinite(value)) throw std::invalid_argument("Non-finite PCA deformation");
        }
    }
    for (const auto& face : faces_) {
        if (face[0] >= directions_.size() || face[1] >= directions_.size()
            || face[2] >= directions_.size()) {
            throw std::invalid_argument("Statistical shape face index is out of range");
        }
    }
}

StatisticalShapeMesh StatisticalFujiShape::mean_shape() const
{
    return sample(std::vector<double>(modes_.size(), 0.0));
}

StatisticalShapeMesh StatisticalFujiShape::sample(
    const std::vector<double>& coefficients_sigma, double sigma_clip) const
{
    if (coefficients_sigma.size() > modes_.size() || sigma_clip <= 0.0) {
        throw std::invalid_argument("Invalid PCA coefficient count or sigma clip");
    }
    std::vector<double> coefficients = coefficients_sigma;
    for (double& coefficient : coefficients) {
        coefficient = std::clamp(coefficient, -sigma_clip, sigma_clip);
    }
    StatisticalShapeMesh mesh;
    mesh.faces = faces_;
    mesh.coefficients_sigma = coefficients;
    mesh.vertices_mm.reserve(directions_.size());
    for (std::size_t vertex = 0; vertex < directions_.size(); ++vertex) {
        double radius = mean_radius_mm_[vertex];
        for (std::size_t mode = 0; mode < coefficients.size(); ++mode) {
            radius += coefficients[mode] * modes_[mode].deformation_mm[vertex];
        }
        if (!std::isfinite(radius) || radius <= 0.0) {
            throw std::invalid_argument(
                "PCA coefficients produced a non-positive radius; reduce sigma clip");
        }
        mesh.vertices_mm.push_back(radius * directions_[vertex]);
    }
    return mesh;
}

StatisticalShapeMesh StatisticalFujiShape::sample_random(
    std::uint64_t seed, std::uint64_t sample_id,
    std::size_t active_modes, double sigma_clip) const
{
    if (active_modes == 0) active_modes = modes_.size();
    if (active_modes > modes_.size()) {
        throw std::invalid_argument("active_modes exceeds available PCA modes");
    }
    CounterRng rng(seed, sample_id);
    std::vector<double> coefficients;
    coefficients.reserve(active_modes);
    while (coefficients.size() < active_modes) {
        const double radius = std::sqrt(-2.0 * std::log(rng.uniform_open()));
        const double angle = 2.0 * kPi * rng.uniform_open();
        coefficients.push_back(radius * std::cos(angle));
        if (coefficients.size() < active_modes) {
            coefficients.push_back(radius * std::sin(angle));
        }
    }
    return sample(coefficients, sigma_clip);
}

} // namespace fruitsim

#pragma once

#include "fruitsim/ray.hpp"

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace fruitsim {

constexpr int kExteriorRegion = -1;

struct SphereLayer {
    std::string name;
    double outer_radius_mm = 0.0;
};

struct BoundaryHit {
    double distance_mm = 0.0;
    Vec3 position{};
    Vec3 normal_from_current{};
    int from_region = kExteriorRegion;
    int to_region = kExteriorRegion;
};

class LayeredSphere {
public:
    LayeredSphere(Vec3 center, std::vector<SphereLayer> inner_to_outer);

    [[nodiscard]] const Vec3& center() const { return center_; }
    [[nodiscard]] const std::vector<SphereLayer>& layers() const { return layers_; }
    [[nodiscard]] double outer_radius_mm() const { return layers_.back().outer_radius_mm; }
    [[nodiscard]] int region_at(const Vec3& point, double tolerance_mm = 1.0e-9) const;
    [[nodiscard]] std::optional<BoundaryHit> next_boundary(
        const Ray& ray, int current_region, double epsilon_mm = 1.0e-8) const;
    [[nodiscard]] std::optional<BoundaryHit> first_entry(
        const Ray& ray, double epsilon_mm = 1.0e-8) const;

private:
    [[nodiscard]] std::vector<double> positive_intersections(
        const Ray& ray, double radius_mm, double epsilon_mm) const;

    Vec3 center_{};
    std::vector<SphereLayer> layers_;
};

} // namespace fruitsim

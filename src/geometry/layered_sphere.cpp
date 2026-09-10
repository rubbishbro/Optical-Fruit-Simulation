#include "fruitsim/geometry/layered_sphere.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace fruitsim {

LayeredSphere::LayeredSphere(Vec3 center, std::vector<SphereLayer> inner_to_outer)
    : center_(center), layers_(std::move(inner_to_outer))
{
    if (layers_.empty()) {
        throw std::invalid_argument("LayeredSphere requires at least one layer");
    }
    double previous = 0.0;
    for (const auto& layer : layers_) {
        if (layer.name.empty() || layer.outer_radius_mm <= previous) {
            throw std::invalid_argument("Layer radii must be positive and strictly increasing");
        }
        previous = layer.outer_radius_mm;
    }
}

int LayeredSphere::region_at(const Vec3& point, double tolerance_mm) const
{
    const double radius = (point - center_).norm();
    for (std::size_t index = 0; index < layers_.size(); ++index) {
        if (radius <= layers_[index].outer_radius_mm + tolerance_mm) {
            return static_cast<int>(index);
        }
    }
    return kExteriorRegion;
}

double LayeredSphere::depth_from_outer_surface(const Vec3& point) const
{
    return std::clamp(outer_radius_mm() - (point - center_).norm(),
        0.0, outer_radius_mm());
}

double LayeredSphere::maximum_depth_along_segment(
    const Vec3& start, const Vec3& end) const
{
    const Vec3 segment = end - start;
    const double length_squared = segment.squared_norm();
    if (length_squared == 0.0) return depth_from_outer_surface(start);
    const double fraction = std::clamp(
        dot(center_ - start, segment) / length_squared, 0.0, 1.0);
    return depth_from_outer_surface(start + fraction * segment);
}

std::vector<double> LayeredSphere::positive_intersections(
    const Ray& ray, double radius_mm, double epsilon_mm) const
{
    const Vec3 offset = ray.origin() - center_;
    const double a = dot(ray.direction(), ray.direction());
    const double half_b = dot(offset, ray.direction());
    const double c = dot(offset, offset) - radius_mm * radius_mm;
    const double discriminant = half_b * half_b - a * c;
    if (discriminant < 0.0) {
        return {};
    }
    const double root = std::sqrt(discriminant);
    std::vector<double> result;
    const double near_t = (-half_b - root) / a;
    const double far_t = (-half_b + root) / a;
    if (near_t > epsilon_mm) {
        result.push_back(near_t);
    }
    if (far_t > epsilon_mm && std::abs(far_t - near_t) > epsilon_mm) {
        result.push_back(far_t);
    }
    return result;
}

std::optional<BoundaryHit> LayeredSphere::next_boundary(
    const Ray& ray, int current_region, double epsilon_mm) const
{
    double best = std::numeric_limits<double>::infinity();
    std::size_t boundary_index = 0;
    for (std::size_t index = 0; index < layers_.size(); ++index) {
        for (const double distance : positive_intersections(
                 ray, layers_[index].outer_radius_mm, epsilon_mm)) {
            const Vec3 after = ray.at(distance + epsilon_mm * 4.0);
            if (region_at(after, 0.0) != current_region && distance < best) {
                best = distance;
                boundary_index = index;
            }
        }
    }
    if (!std::isfinite(best)) {
        return std::nullopt;
    }

    const Vec3 position = ray.at(best);
    const int next_region = region_at(ray.at(best + epsilon_mm * 4.0), 0.0);
    Vec3 outward = (position - center_) / layers_[boundary_index].outer_radius_mm;
    Vec3 normal = outward;
    if (current_region != kExteriorRegion && next_region != kExteriorRegion
        && next_region < current_region) {
        normal = -outward;
    } else if (current_region == kExteriorRegion) {
        normal = -outward;
    }
    return BoundaryHit{best, position, normal, current_region, next_region};
}

std::optional<BoundaryHit> LayeredSphere::first_entry(const Ray& ray, double epsilon_mm) const
{
    if (region_at(ray.origin(), 0.0) != kExteriorRegion) {
        return std::nullopt;
    }
    const auto hits = positive_intersections(ray, outer_radius_mm(), epsilon_mm);
    if (hits.empty()) {
        return std::nullopt;
    }
    const double distance = *std::min_element(hits.begin(), hits.end());
    const Vec3 position = ray.at(distance);
    const Vec3 inward = -(position - center_).normalize();
    return BoundaryHit{
        distance,
        position,
        inward,
        kExteriorRegion,
        static_cast<int>(layers_.size() - 1),
    };
}

} // namespace fruitsim

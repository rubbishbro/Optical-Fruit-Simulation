#include "fruitsim/geometry/mesh_geometry.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

namespace fruitsim {

namespace {
constexpr std::size_t kLeafSize = 8;
constexpr double kInfinity = std::numeric_limits<double>::infinity();

double component(const Vec3& value, int axis)
{
    return axis == 0 ? value.x() : axis == 1 ? value.y() : value.z();
}

Vec3 component_min(const Vec3& lhs, const Vec3& rhs)
{
    return {std::min(lhs.x(), rhs.x()), std::min(lhs.y(), rhs.y()),
        std::min(lhs.z(), rhs.z())};
}

Vec3 component_max(const Vec3& lhs, const Vec3& rhs)
{
    return {std::max(lhs.x(), rhs.x()), std::max(lhs.y(), rhs.y()),
        std::max(lhs.z(), rhs.z())};
}
} // namespace

MeshGeometry::MeshGeometry(StatisticalShapeMesh outer, StatisticalShapeMesh inner,
    Vec3 center)
    : outer_(build_surface(std::move(outer), center)),
      inner_(build_surface(std::move(inner), center)), center_(center)
{
    if (outer_.mesh.faces.empty() || inner_.mesh.faces.empty()) {
        throw std::invalid_argument("MeshGeometry requires non-empty meshes");
    }
    for (const auto& vertex : outer_.mesh.vertices_mm) {
        outer_radius_mm_ = std::max(outer_radius_mm_, (vertex - center_).norm());
    }
    if (outer_radius_mm_ <= 0.0) {
        throw std::invalid_argument("MeshGeometry outer mesh has no positive radius");
    }
}

MeshGeometry::Surface MeshGeometry::build_surface(StatisticalShapeMesh mesh,
    const Vec3& center)
{
    Surface surface;
    surface.mesh = std::move(mesh);
    surface.triangle_bounds.reserve(surface.mesh.faces.size());
    surface.triangle_centroids.reserve(surface.mesh.faces.size());
    surface.triangle_normals.reserve(surface.mesh.faces.size());
    surface.triangle_indices.resize(surface.mesh.faces.size());
    std::iota(surface.triangle_indices.begin(), surface.triangle_indices.end(), 0);
    for (const auto& face : surface.mesh.faces) {
        const Vec3& a = surface.mesh.vertices_mm.at(face[0]);
        const Vec3& b = surface.mesh.vertices_mm.at(face[1]);
        const Vec3& c = surface.mesh.vertices_mm.at(face[2]);
        const Vec3 centroid = (a + b + c) / 3.0;
        Vec3 normal = cross(b - a, c - a).normalize();
        if (dot(normal, centroid - center) < 0.0) normal = -normal;
        surface.triangle_centroids.push_back(centroid);
        surface.triangle_normals.push_back(normal);
        surface.triangle_bounds.push_back({
            component_min(component_min(a, b), c),
            component_max(component_max(a, b), c),
        });
    }
    build_node(surface, 0, surface.triangle_indices.size());
    return surface;
}

int MeshGeometry::build_node(Surface& surface, std::size_t first, std::size_t count)
{
    if (count == 0) return -1;
    Aabb bounds = surface.triangle_bounds.at(surface.triangle_indices[first]);
    Aabb centroid_bounds{surface.triangle_centroids.at(surface.triangle_indices[first]),
        surface.triangle_centroids.at(surface.triangle_indices[first])};
    for (std::size_t index = 1; index < count; ++index) {
        const std::size_t triangle = surface.triangle_indices[first + index];
        bounds = merge_bounds(bounds, surface.triangle_bounds[triangle]);
        centroid_bounds.minimum = component_min(centroid_bounds.minimum,
            surface.triangle_centroids[triangle]);
        centroid_bounds.maximum = component_max(centroid_bounds.maximum,
            surface.triangle_centroids[triangle]);
    }
    const int node_index = static_cast<int>(surface.nodes.size());
    surface.nodes.push_back({bounds});
    if (count <= kLeafSize) {
        surface.nodes[node_index].first = first;
        surface.nodes[node_index].count = count;
        return node_index;
    }
    const Vec3 extent = centroid_bounds.maximum - centroid_bounds.minimum;
    int axis = 0;
    if (component(extent, 1) > component(extent, axis)) axis = 1;
    if (component(extent, 2) > component(extent, axis)) axis = 2;
    const std::size_t middle = first + count / 2;
    std::nth_element(surface.triangle_indices.begin() + static_cast<std::ptrdiff_t>(first),
        surface.triangle_indices.begin() + static_cast<std::ptrdiff_t>(middle),
        surface.triangle_indices.begin() + static_cast<std::ptrdiff_t>(first + count),
        [&](std::size_t lhs, std::size_t rhs) {
            return component(surface.triangle_centroids[lhs], axis)
                < component(surface.triangle_centroids[rhs], axis);
        });
    surface.nodes[node_index].left = build_node(surface, first, middle - first);
    surface.nodes[node_index].right = build_node(surface, middle, first + count - middle);
    return node_index;
}

MeshGeometry::Aabb MeshGeometry::merge_bounds(const Aabb& lhs, const Aabb& rhs)
{
    return {component_min(lhs.minimum, rhs.minimum), component_max(lhs.maximum, rhs.maximum)};
}

bool MeshGeometry::ray_hits_aabb(const Ray& ray, const Aabb& bounds, double maximum_distance)
{
    double near_distance = 0.0;
    double far_distance = maximum_distance;
    for (int axis = 0; axis < 3; ++axis) {
        const double origin = component(ray.origin(), axis);
        const double direction = component(ray.direction(), axis);
        const double minimum = component(bounds.minimum, axis);
        const double maximum = component(bounds.maximum, axis);
        if (std::abs(direction) < 1.0e-15) {
            if (origin < minimum || origin > maximum) return false;
            continue;
        }
        double near_axis = (minimum - origin) / direction;
        double far_axis = (maximum - origin) / direction;
        if (near_axis > far_axis) std::swap(near_axis, far_axis);
        near_distance = std::max(near_distance, near_axis);
        far_distance = std::min(far_distance, far_axis);
        if (near_distance > far_distance) return false;
    }
    return far_distance > 0.0 && near_distance <= maximum_distance;
}

std::optional<BoundaryHit> MeshGeometry::intersect_surface(
    const Surface& surface, const Ray& ray, double epsilon_mm, const Vec3& center)
{
    if (surface.nodes.empty() || !ray_hits_aabb(ray, surface.nodes.front().bounds, kInfinity)) {
        return std::nullopt;
    }
    double best = kInfinity;
    std::size_t best_triangle = 0;
    std::vector<int> stack{0};
    while (!stack.empty()) {
        const int node_index = stack.back();
        stack.pop_back();
        const Node& node = surface.nodes[node_index];
        if (!ray_hits_aabb(ray, node.bounds, best)) continue;
        if (node.count > 0) {
            for (std::size_t offset = 0; offset < node.count; ++offset) {
                const std::size_t triangle = surface.triangle_indices[node.first + offset];
                const auto face = surface.mesh.faces[triangle];
                const Vec3& a = surface.mesh.vertices_mm[face[0]];
                const Vec3& b = surface.mesh.vertices_mm[face[1]];
                const Vec3& c = surface.mesh.vertices_mm[face[2]];
                const Vec3 edge1 = b - a;
                const Vec3 edge2 = c - a;
                const Vec3 pvec = cross(ray.direction(), edge2);
                const double determinant = dot(edge1, pvec);
                if (std::abs(determinant) < 1.0e-14) continue;
                const double inverse = 1.0 / determinant;
                const Vec3 tvec = ray.origin() - a;
                const double u = dot(tvec, pvec) * inverse;
                if (u < -1.0e-10 || u > 1.0 + 1.0e-10) continue;
                const Vec3 qvec = cross(tvec, edge1);
                const double v = dot(ray.direction(), qvec) * inverse;
                if (v < -1.0e-10 || u + v > 1.0 + 1.0e-10) continue;
                const double distance = dot(edge2, qvec) * inverse;
                if (distance > epsilon_mm && distance < best) {
                    best = distance;
                    best_triangle = triangle;
                }
            }
        } else {
            if (node.left >= 0) stack.push_back(node.left);
            if (node.right >= 0) stack.push_back(node.right);
        }
    }
    if (!std::isfinite(best)) return std::nullopt;
    const Vec3 position = ray.at(best);
    Vec3 outward = surface.triangle_normals[best_triangle];
    if (dot(outward, position - center) < 0.0) outward = -outward;
    return BoundaryHit{best, position, outward, kExteriorRegion, kExteriorRegion};
}

double MeshGeometry::radial_surface_radius(const Surface& surface, const Vec3& center,
    const Vec3& direction, double epsilon_mm)
{
    const auto hit = intersect_surface(surface, Ray{center, direction}, epsilon_mm, center);
    return hit ? (hit->position - center).norm() : 0.0;
}

bool MeshGeometry::inside_surface(const Surface& surface, const Vec3& point,
    double tolerance_mm) const
{
    const Vec3 offset = point - center_;
    const double radius = offset.norm();
    if (radius <= tolerance_mm) return true;
    const double surface_radius = radial_surface_radius(
        surface, center_, offset / radius, tolerance_mm);
    return surface_radius > 0.0 && radius <= surface_radius + tolerance_mm;
}

int MeshGeometry::region_at(const Vec3& point, double tolerance_mm) const
{
    if (!inside_surface(outer_, point, tolerance_mm)) return kExteriorRegion;
    return inside_surface(inner_, point, tolerance_mm) ? 0 : 1;
}

std::optional<BoundaryHit> MeshGeometry::boundary_for_surface(
    const Surface& surface, const Ray& ray, double epsilon_mm,
    int current_region, int next_region) const
{
    auto hit = intersect_surface(surface, ray, epsilon_mm, center_);
    if (!hit) return std::nullopt;
    hit->from_region = current_region;
    hit->to_region = next_region;
    const Vec3 outward = hit->normal_from_current;
    hit->normal_from_current = (current_region == kExteriorRegion || next_region < current_region)
        ? -outward : outward;
    return hit;
}

std::optional<BoundaryHit> MeshGeometry::next_boundary(
    const Ray& ray, int current_region, double epsilon_mm) const
{
    if (current_region == kExteriorRegion) {
        return boundary_for_surface(outer_, ray, epsilon_mm, -1, 1);
    }
    if (current_region == 0) {
        return boundary_for_surface(inner_, ray, epsilon_mm, 0, 1);
    }
    if (current_region != 1) return std::nullopt;
    const auto outer_hit = boundary_for_surface(outer_, ray, epsilon_mm, 1, -1);
    const auto inner_hit = boundary_for_surface(inner_, ray, epsilon_mm, 1, 0);
    if (!outer_hit) return inner_hit;
    if (!inner_hit || outer_hit->distance_mm < inner_hit->distance_mm) return outer_hit;
    return inner_hit;
}

std::optional<BoundaryHit> MeshGeometry::first_entry(const Ray& ray, double epsilon_mm) const
{
    if (region_at(ray.origin(), 0.0) != kExteriorRegion) return std::nullopt;
    return boundary_for_surface(outer_, ray, epsilon_mm, -1, 1);
}

double MeshGeometry::depth_from_outer_surface(const Vec3& point) const
{
    if (!inside_surface(outer_, point, 0.0)) return 0.0;
    const Vec3 offset = point - center_;
    if (offset.squared_norm() == 0.0) return outer_radius_mm_;
    const double surface_radius = radial_surface_radius(
        outer_, center_, offset.normalize(), 1.0e-9);
    return std::max(0.0, surface_radius - offset.norm());
}

double MeshGeometry::maximum_depth_along_segment(
    const Vec3& start, const Vec3& end) const
{
    double maximum = 0.0;
    constexpr int samples = 8;
    for (int index = 0; index <= samples; ++index) {
        const double fraction = static_cast<double>(index) / samples;
        maximum = std::max(maximum, depth_from_outer_surface(
            start + fraction * (end - start)));
    }
    return maximum;
}

} // namespace fruitsim

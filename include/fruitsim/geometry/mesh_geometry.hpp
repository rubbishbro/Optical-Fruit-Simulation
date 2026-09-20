#pragma once

#include "fruitsim/geometry/layered_sphere.hpp"
#include "fruitsim/geometry/statistical_fuji_shape.hpp"

#include <optional>
#include <vector>

namespace fruitsim {

// CPU reference geometry for a closed outer mesh and a concentric inner mesh.
// Region 0 is flesh, region 1 is skin, and -1 is exterior.
class MeshGeometry {
public:
    MeshGeometry(StatisticalShapeMesh outer, StatisticalShapeMesh inner,
        Vec3 center = {});

    [[nodiscard]] int region_at(const Vec3& point, double tolerance_mm = 1.0e-9) const;
    [[nodiscard]] std::optional<BoundaryHit> next_boundary(
        const Ray& ray, int current_region, double epsilon_mm = 1.0e-8) const;
    [[nodiscard]] std::optional<BoundaryHit> first_entry(
        const Ray& ray, double epsilon_mm = 1.0e-8) const;
    [[nodiscard]] double depth_from_outer_surface(const Vec3& point) const;
    [[nodiscard]] double maximum_depth_along_segment(
        const Vec3& start, const Vec3& end) const;
    [[nodiscard]] const Vec3& center() const { return center_; }
    [[nodiscard]] double outer_radius_mm() const { return outer_radius_mm_; }
    [[nodiscard]] const StatisticalShapeMesh& outer_mesh() const { return outer_.mesh; }
    [[nodiscard]] const StatisticalShapeMesh& inner_mesh() const { return inner_.mesh; }

private:
    struct Aabb { Vec3 minimum{}; Vec3 maximum{}; };
    struct Node {
        Aabb bounds{};
        int left = -1;
        int right = -1;
        std::size_t first = 0;
        std::size_t count = 0;
    };
    struct Surface {
        StatisticalShapeMesh mesh;
        std::vector<Aabb> triangle_bounds;
        std::vector<Vec3> triangle_centroids;
        std::vector<Vec3> triangle_normals;
        std::vector<std::size_t> triangle_indices;
        std::vector<Node> nodes;
    };

    static Surface build_surface(StatisticalShapeMesh mesh, const Vec3& center);
    static int build_node(Surface& surface, std::size_t first, std::size_t count);
    static Aabb merge_bounds(const Aabb& lhs, const Aabb& rhs);
    static bool ray_hits_aabb(const Ray& ray, const Aabb& bounds, double maximum_distance);
    static std::optional<BoundaryHit> intersect_surface(
        const Surface& surface, const Ray& ray, double epsilon_mm, const Vec3& center);
    static double radial_surface_radius(const Surface& surface, const Vec3& center,
        const Vec3& direction, double epsilon_mm);
    bool inside_surface(const Surface& surface, const Vec3& point,
        double tolerance_mm) const;
    std::optional<BoundaryHit> boundary_for_surface(
        const Surface& surface, const Ray& ray, double epsilon_mm,
        int current_region, int next_region) const;

    Surface outer_;
    Surface inner_;
    Vec3 center_{};
    double outer_radius_mm_ = 0.0;
};

} // namespace fruitsim

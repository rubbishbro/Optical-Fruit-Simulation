#pragma once

#include "fruitsim/vec3.hpp"

#include <ostream>

namespace fruitsim {

class Ray {
public:
    constexpr Ray() = default;
    constexpr Ray(Vec3 origin, Vec3 direction)
        : origin_(origin), direction_(direction)
    {
    }

    [[nodiscard]] constexpr const Vec3& origin() const { return origin_; }
    [[nodiscard]] constexpr const Vec3& direction() const { return direction_; }

    [[nodiscard]] constexpr Vec3 at(double t) const
    {
        return origin_ + t * direction_;
    }

private:
    Vec3 origin_{};
    Vec3 direction_{0.0, 0.0, 1.0};
};

inline std::ostream& operator<<(std::ostream& os, const Ray& ray)
{
    return os << "Ray(origin=" << ray.origin() << ", direction=" << ray.direction() << ")";
}

} // namespace fruitsim

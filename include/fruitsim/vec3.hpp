#pragma once

#include <cmath>
#include <ostream>
#include <stdexcept>

namespace fruitsim {

class Vec3 {
public:
    constexpr Vec3() = default;
    constexpr Vec3(double x, double y, double z) : x_(x), y_(y), z_(z) {}

    [[nodiscard]] constexpr double x() const { return x_; }
    [[nodiscard]] constexpr double y() const { return y_; }
    [[nodiscard]] constexpr double z() const { return z_; }

    [[nodiscard]] constexpr Vec3 operator+() const { return *this; }
    [[nodiscard]] constexpr Vec3 operator-() const { return {-x_, -y_, -z_}; }

    constexpr Vec3& operator+=(const Vec3& rhs)
    {
        x_ += rhs.x_;
        y_ += rhs.y_;
        z_ += rhs.z_;
        return *this;
    }

    constexpr Vec3& operator-=(const Vec3& rhs)
    {
        x_ -= rhs.x_;
        y_ -= rhs.y_;
        z_ -= rhs.z_;
        return *this;
    }

    constexpr Vec3& operator*=(double scale)
    {
        x_ *= scale;
        y_ *= scale;
        z_ *= scale;
        return *this;
    }

    Vec3& operator/=(double scale)
    {
        if (scale == 0.0) {
            throw std::invalid_argument("Vec3 division by zero");
        }
        return *this *= (1.0 / scale);
    }

    [[nodiscard]] double squared_norm() const
    {
        return dot(*this, *this);
    }

    [[nodiscard]] double norm() const
    {
        return std::sqrt(squared_norm());
    }

    [[nodiscard]] Vec3 normalize() const
    {
        const double length = norm();
        if (length == 0.0) {
            throw std::invalid_argument("Cannot normalize a zero-length Vec3");
        }
        return {x_ / length, y_ / length, z_ / length};
    }

    [[nodiscard]] static constexpr double dot(const Vec3& lhs, const Vec3& rhs)
    {
        return lhs.x_ * rhs.x_ + lhs.y_ * rhs.y_ + lhs.z_ * rhs.z_;
    }

    [[nodiscard]] static constexpr Vec3 cross(const Vec3& lhs, const Vec3& rhs)
    {
        return {
            lhs.y_ * rhs.z_ - lhs.z_ * rhs.y_,
            lhs.z_ * rhs.x_ - lhs.x_ * rhs.z_,
            lhs.x_ * rhs.y_ - lhs.y_ * rhs.x_,
        };
    }

private:
    double x_ = 0.0;
    double y_ = 0.0;
    double z_ = 0.0;
};

[[nodiscard]] constexpr Vec3 operator+(Vec3 lhs, const Vec3& rhs)
{
    lhs += rhs;
    return lhs;
}

[[nodiscard]] constexpr Vec3 operator-(Vec3 lhs, const Vec3& rhs)
{
    lhs -= rhs;
    return lhs;
}

[[nodiscard]] constexpr Vec3 operator*(Vec3 lhs, double scale)
{
    lhs *= scale;
    return lhs;
}

[[nodiscard]] constexpr Vec3 operator*(double scale, Vec3 rhs)
{
    rhs *= scale;
    return rhs;
}

[[nodiscard]] inline Vec3 operator/(Vec3 lhs, double scale)
{
    lhs /= scale;
    return lhs;
}

[[nodiscard]] constexpr double dot(const Vec3& lhs, const Vec3& rhs)
{
    return Vec3::dot(lhs, rhs);
}

[[nodiscard]] constexpr Vec3 cross(const Vec3& lhs, const Vec3& rhs)
{
    return Vec3::cross(lhs, rhs);
}

inline std::ostream& operator<<(std::ostream& os, const Vec3& value)
{
    return os << "Vec3(" << value.x() << ", " << value.y() << ", " << value.z() << ")";
}

} // namespace fruitsim

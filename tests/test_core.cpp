#include "fruitsim/random.hpp"
#include "fruitsim/ray.hpp"
#include "fruitsim/vec3.hpp"

#include <cassert>
#include <cmath>

namespace {

bool nearly_equal(double lhs, double rhs, double epsilon = 1.0e-9)
{
    return std::abs(lhs - rhs) <= epsilon;
}

void test_vec3_arithmetic()
{
    const fruitsim::Vec3 a{1.0, 2.0, 3.0};
    const fruitsim::Vec3 b{4.0, -2.0, 0.5};

    const fruitsim::Vec3 sum = a + b;
    assert(nearly_equal(sum.x(), 5.0));
    assert(nearly_equal(sum.y(), 0.0));
    assert(nearly_equal(sum.z(), 3.5));

    assert(nearly_equal(fruitsim::dot(a, b), 1.5));

    const fruitsim::Vec3 cross_product = fruitsim::cross(a, b);
    assert(nearly_equal(cross_product.x(), 7.0));
    assert(nearly_equal(cross_product.y(), 11.5));
    assert(nearly_equal(cross_product.z(), -10.0));
}

void test_vec3_norm()
{
    const fruitsim::Vec3 v{3.0, 4.0, 0.0};

    assert(nearly_equal(v.norm(), 5.0));

    const fruitsim::Vec3 unit = v.normalize();
    assert(nearly_equal(unit.norm(), 1.0));
    assert(nearly_equal(unit.x(), 0.6));
    assert(nearly_equal(unit.y(), 0.8));
}

void test_ray_at()
{
    const fruitsim::Ray ray{{1.0, 2.0, 3.0}, {0.0, -1.0, 2.0}};
    const fruitsim::Vec3 point = ray.at(3.0);

    assert(nearly_equal(point.x(), 1.0));
    assert(nearly_equal(point.y(), -1.0));
    assert(nearly_equal(point.z(), 9.0));
}

void test_random_range()
{
    fruitsim::Random random{123};

    for (int i = 0; i < 100; ++i) {
        const double value01 = random.uniform01();
        assert(value01 >= 0.0);
        assert(value01 <= 1.0);

        const double value = random.uniform(-2.0, 3.0);
        assert(value >= -2.0);
        assert(value <= 3.0);
    }
}

} // namespace

int main()
{
    test_vec3_arithmetic();
    test_vec3_norm();
    test_ray_at();
    test_random_range();

    return 0;
}

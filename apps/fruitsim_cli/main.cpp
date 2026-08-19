#include "fruitsim/random.hpp"
#include "fruitsim/ray.hpp"

#include <iostream>

int main()
{
    fruitsim::Random random{42};

    const fruitsim::Vec3 origin{0.0, 0.0, 0.0};
    const fruitsim::Vec3 direction{1.0, random.uniform(0.1, 0.5), -1.0};
    const fruitsim::Ray ray{origin, direction.normalize()};

    std::cout << "fruitsim ray tracing kernel starter\n";
    std::cout << ray << '\n';
    std::cout << "point at t=2: " << ray.at(2.0) << '\n';

    return 0;
}

#include "fruitsim/random.hpp"

#include <stdexcept>

namespace fruitsim {

Random::Random()
    : engine_(std::random_device{}())
{
}

Random::Random(std::uint32_t seed)
    : engine_(seed)
{
}

double Random::uniform01()
{
    return uniform(0.0, 1.0);
}

double Random::uniform(double min, double max)
{
    if (min > max) {
        throw std::invalid_argument("Random::uniform requires min <= max");
    }

    std::uniform_real_distribution<double> distribution(min, max);
    return distribution(engine_);
}

} // namespace fruitsim

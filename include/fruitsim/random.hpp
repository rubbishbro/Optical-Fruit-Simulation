#pragma once

#include <random>

namespace fruitsim {

class Random {
public:
    Random();
    explicit Random(std::uint32_t seed);

    [[nodiscard]] double uniform01();
    [[nodiscard]] double uniform(double min, double max);

private:
    std::mt19937 engine_;
};

} // namespace fruitsim

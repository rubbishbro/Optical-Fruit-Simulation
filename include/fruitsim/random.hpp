#pragma once

#include <cstdint>
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

// Counter-based Philox4x32-10 stream. A sample depends only on the seed,
// photon id, and draw index, so scheduling never changes a photon path.
class CounterRng {
public:
    CounterRng(std::uint64_t seed, std::uint64_t photon_id);

    [[nodiscard]] std::uint32_t next_u32();
    [[nodiscard]] double uniform_open();

private:
    void refill();

    std::uint64_t seed_ = 0;
    std::uint64_t photon_id_ = 0;
    std::uint64_t block_ = 0;
    std::uint32_t values_[4]{};
    std::uint32_t index_ = 4;
};

} // namespace fruitsim

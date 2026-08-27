#include "fruitsim/random.hpp"

#include <limits>
#include <stdexcept>

namespace fruitsim {

namespace {

constexpr std::uint32_t kPhiloxM0 = 0xD2511F53U;
constexpr std::uint32_t kPhiloxM1 = 0xCD9E8D57U;
constexpr std::uint32_t kPhiloxW0 = 0x9E3779B9U;
constexpr std::uint32_t kPhiloxW1 = 0xBB67AE85U;

std::uint32_t high32(std::uint64_t value)
{
    return static_cast<std::uint32_t>(value >> 32U);
}

} // namespace

Random::Random() : engine_(std::random_device{}()) {}
Random::Random(std::uint32_t seed) : engine_(seed) {}

double Random::uniform01() { return uniform(0.0, 1.0); }

double Random::uniform(double min, double max)
{
    if (min > max) {
        throw std::invalid_argument("Random::uniform requires min <= max");
    }
    return std::uniform_real_distribution<double>(min, max)(engine_);
}

CounterRng::CounterRng(std::uint64_t seed, std::uint64_t photon_id)
    : seed_(seed), photon_id_(photon_id)
{
}

void CounterRng::refill()
{
    std::uint32_t c0 = static_cast<std::uint32_t>(block_);
    std::uint32_t c1 = high32(block_);
    std::uint32_t c2 = static_cast<std::uint32_t>(photon_id_);
    std::uint32_t c3 = high32(photon_id_);
    std::uint32_t k0 = static_cast<std::uint32_t>(seed_);
    std::uint32_t k1 = high32(seed_);

    for (int round = 0; round < 10; ++round) {
        const std::uint64_t p0 = static_cast<std::uint64_t>(kPhiloxM0) * c0;
        const std::uint64_t p1 = static_cast<std::uint64_t>(kPhiloxM1) * c2;
        const std::uint32_t n0 = high32(p1) ^ c1 ^ k0;
        const std::uint32_t n1 = static_cast<std::uint32_t>(p1);
        const std::uint32_t n2 = high32(p0) ^ c3 ^ k1;
        const std::uint32_t n3 = static_cast<std::uint32_t>(p0);
        c0 = n0;
        c1 = n1;
        c2 = n2;
        c3 = n3;
        k0 += kPhiloxW0;
        k1 += kPhiloxW1;
    }

    values_[0] = c0;
    values_[1] = c1;
    values_[2] = c2;
    values_[3] = c3;
    index_ = 0;
    ++block_;
}

std::uint32_t CounterRng::next_u32()
{
    if (index_ == 4) {
        refill();
    }
    return values_[index_++];
}

double CounterRng::uniform_open()
{
    // Map to (0, 1), avoiding log(0) and exact-one branch ambiguities.
    return (static_cast<double>(next_u32()) + 0.5)
        / (static_cast<double>(std::numeric_limits<std::uint32_t>::max()) + 1.0);
}

} // namespace fruitsim

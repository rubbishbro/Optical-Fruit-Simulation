#pragma once

#include "fruitsim/random.hpp"
#include "fruitsim/vec3.hpp"

#include <string>

namespace fruitsim {

struct OpticalProperties {
    double mu_a_mm_inv = 0.0;
    double mu_s_mm_inv = 0.0;
    double g = 0.0;
    double refractive_index = 1.0;

    [[nodiscard]] double mu_t_mm_inv() const { return mu_a_mm_inv + mu_s_mm_inv; }
    void validate(const std::string& context = {}) const;
};

struct FresnelResult {
    double reflectance = 0.0;
    double cos_transmitted = 1.0;
    bool total_internal_reflection = false;
};

[[nodiscard]] FresnelResult fresnel_unpolarized(
    double cos_incident, double n_incident, double n_transmitted);
[[nodiscard]] Vec3 reflect_direction(const Vec3& incident, const Vec3& normal);
[[nodiscard]] Vec3 refract_direction(
    const Vec3& incident, const Vec3& normal_from_incident, double n_incident,
    double n_transmitted);
[[nodiscard]] double sample_henyey_greenstein_cosine(double g, CounterRng& rng);
[[nodiscard]] Vec3 scatter_henyey_greenstein(
    const Vec3& incident, double g, CounterRng& rng);

} // namespace fruitsim

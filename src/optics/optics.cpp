#include "fruitsim/optics/optics.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace fruitsim {

namespace {
constexpr double kPi = 3.14159265358979323846;
}

void OpticalProperties::validate(const std::string& context) const
{
    const std::string prefix = context.empty() ? std::string{} : context + ": ";
    if (mu_a_mm_inv < 0.0 || mu_s_mm_inv < 0.0) {
        throw std::invalid_argument(prefix + "optical coefficients must be non-negative");
    }
    if (g < -1.0 || g >= 1.0) {
        throw std::invalid_argument(prefix + "g must be in [-1, 1)");
    }
    if (refractive_index <= 0.0) {
        throw std::invalid_argument(prefix + "refractive index must be positive");
    }
}

FresnelResult fresnel_unpolarized(
    double cos_incident, double n_incident, double n_transmitted)
{
    if (n_incident <= 0.0 || n_transmitted <= 0.0) {
        throw std::invalid_argument("Fresnel refractive indices must be positive");
    }
    const double ci = std::clamp(cos_incident, 0.0, 1.0);
    const double eta = n_incident / n_transmitted;
    const double sin_t_squared = eta * eta * std::max(0.0, 1.0 - ci * ci);
    if (sin_t_squared >= 1.0) {
        return {1.0, 0.0, true};
    }
    const double ct = std::sqrt(std::max(0.0, 1.0 - sin_t_squared));
    const double rs_den = n_incident * ci + n_transmitted * ct;
    const double rp_den = n_incident * ct + n_transmitted * ci;
    const double rs = rs_den == 0.0 ? 1.0
                                    : (n_incident * ci - n_transmitted * ct) / rs_den;
    const double rp = rp_den == 0.0 ? 1.0
                                    : (n_incident * ct - n_transmitted * ci) / rp_den;
    return {0.5 * (rs * rs + rp * rp), ct, false};
}

Vec3 reflect_direction(const Vec3& incident, const Vec3& normal)
{
    return (incident - 2.0 * dot(incident, normal) * normal).normalize();
}

Vec3 refract_direction(
    const Vec3& incident, const Vec3& normal_from_incident, double n_incident,
    double n_transmitted)
{
    const double cos_i = std::clamp(dot(incident, normal_from_incident), 0.0, 1.0);
    const double eta = n_incident / n_transmitted;
    const Vec3 tangent = incident - cos_i * normal_from_incident;
    const double tangent_squared = tangent.squared_norm();
    const double transmitted_tangent_squared = eta * eta * tangent_squared;
    if (transmitted_tangent_squared >= 1.0) {
        throw std::domain_error("Refraction requested during total internal reflection");
    }
    const double cos_t = std::sqrt(1.0 - transmitted_tangent_squared);
    return (eta * tangent + cos_t * normal_from_incident).normalize();
}

double sample_henyey_greenstein_cosine(double g, CounterRng& rng)
{
    const double xi = rng.uniform_open();
    if (std::abs(g) < 1.0e-12) {
        return 2.0 * xi - 1.0;
    }
    const double ratio = (1.0 - g * g) / (1.0 - g + 2.0 * g * xi);
    return std::clamp((1.0 + g * g - ratio * ratio) / (2.0 * g), -1.0, 1.0);
}

Vec3 scatter_henyey_greenstein(const Vec3& incident, double g, CounterRng& rng)
{
    const Vec3 w = incident.normalize();
    const Vec3 helper = std::abs(w.z()) < 0.999 ? Vec3{0.0, 0.0, 1.0}
                                                : Vec3{1.0, 0.0, 0.0};
    const Vec3 u = cross(helper, w).normalize();
    const Vec3 v = cross(w, u);
    const double cos_theta = sample_henyey_greenstein_cosine(g, rng);
    const double sin_theta = std::sqrt(std::max(0.0, 1.0 - cos_theta * cos_theta));
    const double phi = 2.0 * kPi * rng.uniform_open();
    return (sin_theta * std::cos(phi) * u + sin_theta * std::sin(phi) * v
            + cos_theta * w)
        .normalize();
}

} // namespace fruitsim

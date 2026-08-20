#include "fruitsim/transport/monte_carlo.hpp"

#include "fruitsim/optics/optics.hpp"
#include "fruitsim/random.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace fruitsim {

namespace {

constexpr double kPi = 3.14159265358979323846;

std::size_t grid_index(const SimulationProblem& problem, const Vec3& point)
{
    const std::size_t size = problem.scoring.grid_size;
    const double radius = problem.domain.outer_radius_mm();
    const Vec3 local = point - problem.domain.center();
    const auto axis = [size, radius](double value) {
        const double normalized = (value + radius) / (2.0 * radius);
        const auto index = static_cast<long long>(std::floor(normalized * size));
        return static_cast<std::size_t>(std::clamp<long long>(index, 0, size - 1));
    };
    const std::size_t x = axis(local.x());
    const std::size_t y = axis(local.y());
    const std::size_t z = axis(local.z());
    return (z * size + y) * size + x;
}

std::size_t radial_bin(const SimulationProblem& problem, const Vec3& point, const Vec3& entry)
{
    const Vec3 axis = problem.source.direction.normalize();
    const Vec3 offset = point - entry;
    const Vec3 radial = offset - dot(offset, axis) * axis;
    const double radius = radial.norm();
    const double scaled = radius / problem.scoring.radial_max_mm
        * static_cast<double>(problem.scoring.radial_bins);
    return std::min(
        problem.scoring.radial_bins - 1,
        static_cast<std::size_t>(std::max(0.0, std::floor(scaled))));
}

void record_trajectory(
    BatchResult& result, const SimulationProblem& problem, const PhotonState& photon)
{
    if (photon.photon_id < problem.scoring.trajectory_limit) {
        result.trajectories.push_back({
            photon.photon_id,
            photon.event_count,
            photon.position_mm,
            photon.weight,
            photon.region,
        });
    }
}

double medium_index(
    const SimulationProblem& problem, const SpectralMedium& spectrum, int region)
{
    return region == kExteriorRegion
        ? problem.exterior_refractive_index
        : spectrum.regions.at(static_cast<std::size_t>(region)).refractive_index;
}

} // namespace

void SimulationProblem::validate() const
{
    if (metadata.transport_mode != "scalar") {
        throw std::invalid_argument("Only scalar transport_mode is currently supported");
    }
    if (spectra.empty()) {
        throw std::invalid_argument("At least one wavelength is required");
    }
    if (source.direction.squared_norm() == 0.0) {
        throw std::invalid_argument("Source direction cannot be zero");
    }
    if ((source.type != "pencil" && source.type != "gaussian")
        || source.gaussian_sigma_mm < 0.0
        || (source.type == "gaussian" && source.gaussian_sigma_mm == 0.0)) {
        throw std::invalid_argument("Source must be pencil or gaussian with positive sigma");
    }
    if (exterior_refractive_index <= 0.0) {
        throw std::invalid_argument("Exterior refractive index must be positive");
    }
    if (execution.photons_per_wavelength == 0 || execution.batch_size == 0
        || execution.max_reduction_batches == 0) {
        throw std::invalid_argument("Photon and batch counts must be positive");
    }
    if (execution.roulette_threshold < 0.0 || execution.roulette_survival <= 0.0
        || execution.roulette_survival > 1.0) {
        throw std::invalid_argument("Invalid roulette settings");
    }
    if (scoring.radial_bins == 0 || scoring.radial_max_mm <= 0.0
        || scoring.depth_bins == 0) {
        throw std::invalid_argument("Scoring bin counts and ranges must be positive");
    }
    for (const auto& spectrum : spectra) {
        if (spectrum.wavelength_nm <= 0.0
            || spectrum.regions.size() != domain.layers().size()) {
            throw std::invalid_argument("Each wavelength must define every sphere region");
        }
        for (std::size_t region = 0; region < spectrum.regions.size(); ++region) {
            spectrum.regions[region].validate(domain.layers()[region].name);
        }
    }
}

BatchResult simulate_batch(
    const SimulationProblem& problem, std::size_t wavelength_index,
    std::uint64_t first_photon, std::uint64_t photon_count)
{
    const auto& spectrum = problem.spectra.at(wavelength_index);
    BatchResult result;
    result.photon_count = photon_count;
    result.absorbed.assign(problem.domain.layers().size(), 0.0);
    result.radial_reflectance.assign(problem.scoring.radial_bins, 0.0);
    result.depth_histogram.assign(problem.scoring.depth_bins, 0);
    if (problem.scoring.grid_size > 0) {
        const std::size_t size = problem.scoring.grid_size;
        result.absorption_grid.assign(size * size * size, 0.0);
    }

    const Vec3 source_direction = problem.source.direction.normalize();
    const Vec3 helper = std::abs(source_direction.z()) < 0.999
        ? Vec3{0.0, 0.0, 1.0}
        : Vec3{1.0, 0.0, 0.0};
    const Vec3 source_u = cross(helper, source_direction).normalize();
    const Vec3 source_v = cross(source_direction, source_u);

    for (std::uint64_t offset = 0; offset < photon_count; ++offset) {
        const std::uint64_t photon_id = first_photon + offset;
        CounterRng rng(problem.execution.seed + wavelength_index, photon_id);
        Vec3 launch_position = problem.source.position_mm;
        if (problem.source.type == "gaussian") {
            const double radius = problem.source.gaussian_sigma_mm
                * std::sqrt(-2.0 * std::log(rng.uniform_open()));
            const double phi = 2.0 * kPi * rng.uniform_open();
            launch_position += radius * std::cos(phi) * source_u
                + radius * std::sin(phi) * source_v;
        }
        const auto entry = problem.domain.first_entry(
            Ray{launch_position, source_direction}, problem.execution.boundary_epsilon_mm);
        if (!entry) {
            result.discarded += 1.0;
            continue;
        }
        PhotonState photon;
        photon.photon_id = photon_id;
        photon.wavelength_index = wavelength_index;
        photon.position_mm = entry->position;
        photon.direction = source_direction;

        const int outer_region = entry->to_region;
        const double n_inside = medium_index(problem, spectrum, outer_region);
        const double cos_i = std::clamp(dot(photon.direction, entry->normal_from_current), 0.0, 1.0);
        const auto entry_fresnel = fresnel_unpolarized(
            cos_i, problem.exterior_refractive_index, n_inside);
        result.reflected += entry_fresnel.reflectance;
        result.radial_reflectance[0] += entry_fresnel.reflectance;
        photon.weight = 1.0 - entry_fresnel.reflectance;
        if (photon.weight <= 0.0) {
            continue;
        }
        photon.direction = refract_direction(
            photon.direction, entry->normal_from_current,
            problem.exterior_refractive_index, n_inside);
        photon.position_mm += problem.execution.boundary_epsilon_mm * photon.direction;
        photon.region = outer_region;
        record_trajectory(result, problem, photon);

        double maximum_depth = 0.0;
        bool alive = true;
        while (alive && photon.event_count < problem.execution.max_events) {
            double optical_depth = -std::log(rng.uniform_open());
            bool reached_collision = false;

            while (alive && !reached_collision
                   && photon.event_count < problem.execution.max_events) {
                const auto& properties = spectrum.regions.at(
                    static_cast<std::size_t>(photon.region));
                const double mu_t = properties.mu_t_mm_inv();
                const auto boundary = problem.domain.next_boundary(
                    Ray{photon.position_mm, photon.direction}, photon.region,
                    problem.execution.boundary_epsilon_mm);
                if (!boundary) {
                    result.discarded += photon.weight;
                    alive = false;
                    break;
                }
                const double collision_distance = mu_t > 0.0
                    ? optical_depth / mu_t
                    : std::numeric_limits<double>::infinity();

                if (collision_distance < boundary->distance_mm) {
                    photon.position_mm += collision_distance * photon.direction;
                    maximum_depth = std::max(
                        maximum_depth,
                        std::max(0.0, dot(photon.position_mm - entry->position, source_direction)));
                    const double absorbed = mu_t > 0.0
                        ? photon.weight * properties.mu_a_mm_inv / mu_t
                        : 0.0;
                    result.absorbed[static_cast<std::size_t>(photon.region)] += absorbed;
                    if (!result.absorption_grid.empty() && absorbed > 0.0) {
                        result.absorption_grid[grid_index(problem, photon.position_mm)] += absorbed;
                    }
                    photon.weight -= absorbed;
                    ++photon.event_count;
                    record_trajectory(result, problem, photon);
                    if (properties.mu_s_mm_inv <= 0.0 || photon.weight <= 0.0) {
                        alive = false;
                        reached_collision = true;
                        break;
                    }
                    photon.direction = scatter_henyey_greenstein(
                        photon.direction, properties.g, rng);
                    reached_collision = true;
                } else {
                    photon.position_mm = boundary->position;
                    if (mu_t > 0.0) {
                        optical_depth = std::max(
                            0.0, optical_depth - mu_t * boundary->distance_mm);
                    }
                    const double n1 = medium_index(problem, spectrum, photon.region);
                    const double n2 = medium_index(problem, spectrum, boundary->to_region);
                    const double boundary_cos = std::clamp(
                        dot(photon.direction, boundary->normal_from_current), 0.0, 1.0);
                    const auto fresnel = fresnel_unpolarized(boundary_cos, n1, n2);
                    ++photon.event_count;
                    if (fresnel.total_internal_reflection
                        || rng.uniform_open() < fresnel.reflectance) {
                        photon.direction = reflect_direction(
                            photon.direction, boundary->normal_from_current);
                        photon.position_mm += problem.execution.boundary_epsilon_mm
                            * photon.direction;
                        record_trajectory(result, problem, photon);
                        continue;
                    }

                    photon.direction = refract_direction(
                        photon.direction, boundary->normal_from_current, n1, n2);
                    photon.region = boundary->to_region;
                    photon.position_mm += problem.execution.boundary_epsilon_mm
                        * photon.direction;
                    record_trajectory(result, problem, photon);
                    if (photon.region == kExteriorRegion) {
                        const bool reflected = dot(
                            boundary->normal_from_current, source_direction) < 0.0;
                        if (reflected) {
                            result.reflected += photon.weight;
                            result.radial_reflectance[radial_bin(
                                problem, boundary->position, entry->position)] += photon.weight;
                        } else {
                            result.transmitted += photon.weight;
                        }
                        alive = false;
                    }
                }
            }

            if (alive && photon.weight < problem.execution.roulette_threshold) {
                if (rng.uniform_open() <= problem.execution.roulette_survival) {
                    photon.weight /= problem.execution.roulette_survival;
                } else {
                    result.discarded += photon.weight;
                    alive = false;
                }
            }
        }

        if (alive) {
            result.discarded += photon.weight;
        }
        const double max_depth = 2.0 * problem.domain.outer_radius_mm();
        const std::size_t depth_bin = std::min(
            problem.scoring.depth_bins - 1,
            static_cast<std::size_t>(maximum_depth / max_depth
                * static_cast<double>(problem.scoring.depth_bins)));
        ++result.depth_histogram[depth_bin];
    }

    return result;
}

} // namespace fruitsim

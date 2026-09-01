#include "fruitsim/geometry/layered_sphere.hpp"
#include "fruitsim/geometry/statistical_fuji_shape.hpp"
#include "fruitsim/optics/optics.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"
#include "fruitsim/transport/monte_carlo.hpp"

#include <cassert>
#include <array>
#include <cmath>
#include <numeric>
#include <vector>

namespace {

bool close(double left, double right, double tolerance = 1.0e-10)
{
    return std::abs(left - right) <= tolerance;
}

fruitsim::SimulationProblem simple_problem()
{
    fruitsim::SimulationProblem problem{
        fruitsim::LayeredSphere{{0, 0, 0}, {{"flesh", 10.0}}},
    };
    problem.source.position_mm = {0, 0, -12};
    problem.source.direction = {0, 0, 1};
    problem.exterior_refractive_index = 1.0;
    problem.spectra = {{800.0, {{0.02, 1.0, 0.8, 1.0}}}};
    problem.execution.photons_per_wavelength = 4000;
    problem.execution.batch_size = 250;
    problem.execution.seed = 1234;
    problem.execution.roulette_threshold = 0.0;
    problem.execution.max_events = 10000;
    problem.scoring.radial_bins = 10;
    problem.scoring.radial_max_mm = 10;
    problem.scoring.depth_bins = 20;
    return problem;
}

void test_geometry()
{
    const fruitsim::LayeredSphere sphere{
        {0, 0, 0}, {{"core", 2.0}, {"flesh", 9.0}, {"skin", 10.0}}};
    assert(sphere.region_at({0, 0, 0}) == 0);
    assert(sphere.region_at({3, 0, 0}) == 1);
    assert(sphere.region_at({9.5, 0, 0}) == 2);
    assert(sphere.region_at({11, 0, 0}) == fruitsim::kExteriorRegion);
    assert(close(sphere.depth_from_outer_surface({0, 0, 10}), 0.0));
    assert(close(sphere.depth_from_outer_surface({0, 0, 6}), 4.0));
    assert(close(sphere.depth_from_outer_surface({0, 0, 0}), 10.0));
    assert(close(sphere.depth_from_outer_surface({0, 0, 12}), 0.0));
    assert(close(sphere.maximum_depth_along_segment(
        {0, 0, -10}, {0, 0, 10}), 10.0));
    assert(close(sphere.maximum_depth_along_segment(
        {6, 0, -8}, {6, 0, 8}), 4.0));
    const auto entry = sphere.first_entry({{0, 0, -12}, {0, 0, 1}});
    assert(entry);
    assert(close(entry->distance_mm, 2.0));
    assert(entry->to_region == 2);
    const auto next = sphere.next_boundary({{0, 0, -9.9}, {0, 0, 1}}, 2);
    assert(next);
    assert(next->to_region == 1);
}

void test_statistical_shape_sampling()
{
    const std::vector<fruitsim::Vec3> directions{
        {1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}, {0, 0, 1}, {0, 0, -1},
    };
    fruitsim::StatisticalShapeMode mode;
    mode.eigenvalue_mm2 = 4.0;
    mode.explained_variance_ratio = 1.0;
    mode.deformation_mm = {2, 2, -1, -1, 0.5, 0.5};
    const std::vector<std::array<std::size_t, 3>> faces{
        {0, 2, 4}, {2, 1, 4}, {1, 3, 4}, {3, 0, 4},
        {2, 0, 5}, {1, 2, 5}, {3, 1, 5}, {0, 3, 5},
    };
    const fruitsim::StatisticalFujiShape shape(
        directions, std::vector<double>(6, 40.0), {mode}, faces,
        "unverified_in_source_record", "10.5281/zenodo.15635995");
    const auto deformed = shape.sample({1.5});
    assert(close(deformed.vertices_mm[0].x(), 43.0));
    assert(close(deformed.vertices_mm[2].y(), 38.5));
    const auto first = shape.sample_random(123, 7, 1);
    const auto second = shape.sample_random(123, 7, 1);
    assert(first.vertices_mm.size() == directions.size());
    for (std::size_t index = 0; index < first.vertices_mm.size(); ++index) {
        assert(first.vertices_mm[index].x() == second.vertices_mm[index].x());
        assert(first.vertices_mm[index].y() == second.vertices_mm[index].y());
        assert(first.vertices_mm[index].z() == second.vertices_mm[index].z());
    }
}

void test_fresnel()
{
    const auto matched = fruitsim::fresnel_unpolarized(1.0, 1.36, 1.36);
    assert(close(matched.reflectance, 0.0));
    const auto normal = fruitsim::fresnel_unpolarized(1.0, 1.0, 1.5);
    assert(close(normal.reflectance, 0.04, 1.0e-12));
    const auto tir = fruitsim::fresnel_unpolarized(0.5, 1.5, 1.0);
    assert(tir.total_internal_reflection);
}

void test_hg_mean()
{
    fruitsim::CounterRng rng{99, 7};
    constexpr double expected_g = 0.75;
    double sum = 0.0;
    constexpr int samples = 200000;
    for (int index = 0; index < samples; ++index) {
        sum += fruitsim::sample_henyey_greenstein_cosine(expected_g, rng);
    }
    assert(std::abs(sum / samples - expected_g) < 0.006);
}

void test_transport_determinism_and_energy()
{
    auto problem = simple_problem();
    fruitsim::CpuTransportBackend backend;
    problem.execution.threads = 1;
    const auto serial = backend.run(problem);
    problem.execution.threads = 4;
    const auto parallel = backend.run(problem);
    const auto& a = serial.wavelengths.front();
    const auto& b = parallel.wavelengths.front();
    assert(a.reflectance == b.reflectance);
    assert(a.transmittance == b.transmittance);
    assert(a.absorbed_by_region == b.absorbed_by_region);
    assert(a.boundary_failures == 0);
    assert(a.max_event_terminations == 0);
    assert(std::abs(a.energy_residual) < 1.0e-10);
}

void test_beer_lambert()
{
    auto problem = simple_problem();
    problem.spectra = {{800.0, {{0.05, 0.0, 0.0, 1.0}}}};
    problem.execution.photons_per_wavelength = 50000;
    problem.execution.batch_size = 1000;
    problem.execution.threads = 4;
    fruitsim::CpuTransportBackend backend;
    const auto result = backend.run(problem).wavelengths.front();
    const double expected_transmission = std::exp(-0.05 * 20.0);
    assert(std::abs(result.transmittance - expected_transmission) < 0.01);
    assert(std::abs(result.reflectance) < 1.0e-12);
    assert(std::abs(result.energy_residual) < 1.0e-12);
}

void test_gaussian_source()
{
    auto problem = simple_problem();
    problem.source.type = "gaussian";
    problem.source.gaussian_sigma_mm = 1.0;
    problem.execution.photons_per_wavelength = 1000;
    fruitsim::CpuTransportBackend backend;
    const auto result = backend.run(problem).wavelengths.front();
    assert(result.photons == 1000);
    assert(std::isfinite(result.energy_residual));
}

void test_ring_source_area_sampling()
{
    fruitsim::PhotonSource source;
    source.type = "ring";
    source.position_mm = {1.0, -2.0, 3.0};
    source.direction = {0.0, 0.0, 1.0};
    source.ring_plane_normal = {0.0, 0.0, 1.0};
    source.ring_radius_mm = 5.0;
    source.ring_width_mm = 2.0;
    source.spatial_sampling = "uniform_area";
    fruitsim::CounterRng rng{12345, 99};
    constexpr int samples = 100000;
    double mean_x = 0.0;
    double mean_y = 0.0;
    double mean_radius_squared = 0.0;
    for (int index = 0; index < samples; ++index) {
        const auto launch = fruitsim::sample_source_launch(source, rng);
        const auto local = launch.position_mm - source.position_mm;
        assert(std::abs(local.z()) < 1.0e-12);
        const double radius_squared = local.x() * local.x() + local.y() * local.y();
        assert(radius_squared >= 16.0 && radius_squared <= 36.0);
        mean_x += local.x();
        mean_y += local.y();
        mean_radius_squared += radius_squared;
    }
    mean_x /= samples;
    mean_y /= samples;
    mean_radius_squared /= samples;
    assert(std::abs(mean_x) < 0.04);
    assert(std::abs(mean_y) < 0.04);
    // Uniform annulus area gives E[r^2] = (r_inner^2 + r_outer^2) / 2.
    assert(std::abs(mean_radius_squared - 26.0) < 0.12);
}

void test_ring_uniform_azimuth_and_per_sample_aim()
{
    fruitsim::PhotonSource source;
    source.type = "ring";
    source.position_mm = {2.0, -1.0, -5.0};
    source.ring_plane_normal = {1.0, 2.0, 3.0};
    source.ring_radius_mm = 4.0;
    source.ring_width_mm = 0.0;
    source.spatial_sampling = "uniform_azimuth";
    source.direction_mode = "aim_at";
    source.target_mm = {-3.0, 2.0, 1.0};
    fruitsim::CounterRng rng{34567, 12};
    constexpr int samples = 50000;
    fruitsim::Vec3 mean_offset{};
    fruitsim::Vec3 first_direction{};
    for (int index = 0; index < samples; ++index) {
        const auto launch = fruitsim::sample_source_launch(source, rng);
        const auto offset = launch.position_mm - source.position_mm;
        assert(std::abs(offset.norm() - source.ring_radius_mm) < 1.0e-10);
        assert(std::abs(fruitsim::dot(offset,
            source.ring_plane_normal.normalize())) < 1.0e-10);
        const auto expected = (source.target_mm - launch.position_mm).normalize();
        assert((launch.direction - expected).norm() < 1.0e-12);
        if (index == 0) first_direction = launch.direction;
        mean_offset += offset;
    }
    mean_offset /= static_cast<double>(samples);
    assert(mean_offset.norm() < 0.04);
    const auto another = fruitsim::sample_source_launch(source, rng);
    assert((another.direction - first_direction).norm() > 1.0e-3);
}

void test_rotated_detector_and_exterior_na()
{
    fruitsim::CircularDetector detector;
    detector.enabled = true;
    detector.center_mm = {3.0, -1.0, 4.0};
    detector.axis = fruitsim::Vec3{1.0, 2.0, 2.0}.normalize();
    detector.radius_mm = 1.0;
    detector.acceptance_half_angle_deg = 20.0;
    const auto axis = detector.axis;
    const auto tangent = fruitsim::cross(axis, fruitsim::Vec3{0.0, 0.0, 1.0}).normalize();
    const auto escape = detector.center_mm + 2.0 * axis;
    assert(fruitsim::detector_accepts(detector, escape, -axis));
    assert(fruitsim::detector_accepts(detector, escape + 0.5 * tangent, -axis));
    assert(!fruitsim::detector_accepts(detector, escape + 1.5 * tangent, -axis));
    assert(!fruitsim::detector_accepts(detector, escape, axis));

    const double angle = fruitsim::detector_acceptance_half_angle_degrees(0.5, 1.33);
    assert(close(angle, std::asin(0.5 / 1.33) * 180.0
        / 3.14159265358979323846, 1.0e-12));
}

fruitsim::SimulationProblem detector_problem()
{
    fruitsim::SimulationProblem problem{
        fruitsim::LayeredSphere{{0, 0, 0}, {{"flesh", 9.0}, {"skin", 10.0}}},
    };
    problem.source.position_mm = {0, 0, -12};
    problem.source.direction = {0, 0, 1};
    problem.detector.enabled = true;
    problem.detector.center_mm = {0, 0, -10.1};
    problem.detector.axis = {0, 0, 1};
    problem.detector.radius_mm = 2.0;
    problem.detector.acceptance_half_angle_deg = 45.0;
    problem.spectra = {{800.0, {
        {0.02, 1.0, 0.8, 1.0},
        {0.04, 1.2, 0.8, 1.0},
    }}};
    problem.execution.photons_per_wavelength = 10000;
    problem.execution.batch_size = 500;
    problem.execution.seed = 2468;
    problem.execution.roulette_threshold = 0.0;
    problem.execution.max_events = 10000;
    problem.scoring.radial_bins = 20;
    problem.scoring.radial_max_mm = 10.0;
    problem.scoring.depth_bins = 40;
    return problem;
}

void test_detector_filter_monotonicity_and_invariance()
{
    fruitsim::CpuTransportBackend backend;
    auto small = detector_problem();
    small.detector.radius_mm = 0.5;
    small.detector.acceptance_half_angle_deg = 20.0;
    const auto small_result = backend.run(small).wavelengths.front();

    auto large_radius = small;
    large_radius.detector.radius_mm = 3.0;
    const auto radius_result = backend.run(large_radius).wavelengths.front();
    assert(radius_result.detected_weight >= small_result.detected_weight);

    auto large_angle = small;
    large_angle.detector.acceptance_half_angle_deg = 80.0;
    const auto angle_result = backend.run(large_angle).wavelengths.front();
    assert(angle_result.detected_weight >= small_result.detected_weight);

    auto disabled = small;
    disabled.detector.enabled = false;
    const auto disabled_result = backend.run(disabled).wavelengths.front();
    assert(disabled_result.detected_weight == 0.0);
    assert(disabled_result.detected_photon_count == 0);
    // Detector scoring is a pure observation and consumes no random values.
    assert(disabled_result.reflectance == small_result.reflectance);
    assert(disabled_result.transmittance == small_result.transmittance);
    assert(disabled_result.absorbed_by_region == small_result.absorbed_by_region);
    assert(disabled_result.discarded_weight == small_result.discarded_weight);
    assert(disabled_result.energy_residual == small_result.energy_residual);
}

void test_ideal_detector_and_detected_path_statistics()
{
    auto ideal = simple_problem();
    ideal.spectra = {{800.0, {{0.0, 0.0, 0.0, 1.5}}}};
    ideal.detector.enabled = true;
    ideal.detector.center_mm = {0, 0, -10.001};
    ideal.detector.axis = {0, 0, 1};
    ideal.detector.radius_mm = 100.0;
    ideal.detector.acceptance_half_angle_deg = 90.0;
    fruitsim::CpuTransportBackend backend;
    const auto ideal_result = backend.run(ideal).wavelengths.front();
    // Two refractive interfaces give the incoherent slab/sphere normal-incidence
    // total R = 2*R0/(1+R0), including internal Fresnel returns.
    const double expected_total_reflectance = 2.0 * 0.04 / 1.04;
    assert(std::abs(ideal_result.reflectance - expected_total_reflectance) < 0.005);
    assert(std::abs(ideal_result.detected_reflectance - ideal_result.reflectance) < 1.0e-3);
    assert(close(ideal_result.detected_weight,
        ideal_result.detected_specular_weight + ideal_result.detected_diffuse_weight));
    assert(std::abs(ideal_result.detected_specular_weight
        / ideal_result.photons - 0.04) < 1.0e-12);
    assert(ideal_result.detected_diffuse_weight > 0.0);
    assert(std::abs(ideal_result.energy_residual) < 1.0e-12);

    auto layered = detector_problem();
    layered.detector.radius_mm = 4.0;
    layered.detector.acceptance_half_angle_deg = 90.0;
    const auto paths = backend.run(layered).wavelengths.front();
    assert(paths.detected_weight > 0.0);
    assert(paths.detected_reflectance <= paths.reflectance + 1.0e-12);
    assert(paths.detected_penetration_mean_mm >= 0.0);
    assert(paths.detected_penetration_median_mm >= 0.0);
    assert(paths.detected_penetration_mean_mm <= layered.domain.outer_radius_mm());
    assert(paths.weighted_mean_total_path_mm >= 0.0);
    assert(paths.weighted_mean_path_by_region_mm.size() == layered.domain.layers().size());
    assert(paths.path_fraction_by_region.size() == layered.domain.layers().size());
    assert(close(paths.detected_weight,
        paths.detected_specular_weight + paths.detected_diffuse_weight));
    assert(close(paths.weighted_mean_skin_path_mm
            + paths.weighted_mean_flesh_path_mm,
        paths.weighted_mean_total_path_mm));
    assert(paths.skin_path_fraction >= 0.0 && paths.skin_path_fraction <= 1.0);
    assert(paths.flesh_path_fraction >= 0.0 && paths.flesh_path_fraction <= 1.0);
    assert(std::abs(paths.skin_path_fraction + paths.flesh_path_fraction - 1.0) < 1.0e-10);
}

void test_detector_thread_determinism()
{
    auto problem = detector_problem();
    fruitsim::CpuTransportBackend backend;
    problem.execution.threads = 1;
    const auto serial = backend.run(problem).wavelengths.front();
    problem.execution.threads = 4;
    const auto parallel = backend.run(problem).wavelengths.front();
    assert(serial.detected_photon_count == parallel.detected_photon_count);
    assert(serial.detected_weight == parallel.detected_weight);
    assert(serial.detected_specular_weight == parallel.detected_specular_weight);
    assert(serial.detected_diffuse_weight == parallel.detected_diffuse_weight);
    assert(serial.detected_penetration_mean_mm == parallel.detected_penetration_mean_mm);
    assert(serial.detected_penetration_median_mm == parallel.detected_penetration_median_mm);
    assert(serial.skin_path_fraction == parallel.skin_path_fraction);
    assert(serial.flesh_path_fraction == parallel.flesh_path_fraction);
    assert(serial.weighted_mean_path_by_region_mm
        == parallel.weighted_mean_path_by_region_mm);
    assert(serial.path_fraction_by_region == parallel.path_fraction_by_region);
}

void test_ring_transport()
{
    auto problem = detector_problem();
    problem.source.type = "ring";
    problem.source.position_mm = {0, 0, -12};
    problem.source.ring_plane_normal = {0, 0, 1};
    problem.source.ring_radius_mm = 3.0;
    problem.source.ring_width_mm = 1.0;
    problem.source.spatial_sampling = "uniform_area";
    problem.source.direction_mode = "aim_at";
    problem.source.target_mm = {0, 0, 0};
    problem.execution.photons_per_wavelength = 6000;
    fruitsim::CpuTransportBackend backend;
    const auto result = backend.run(problem).wavelengths.front();
    assert(result.photons == 6000);
    assert(result.boundary_failures == 0);
    assert(result.max_event_terminations == 0);
    assert(std::abs(result.energy_residual) < 1.0e-10);
}

} // namespace

int main()
{
    test_geometry();
    test_statistical_shape_sampling();
    test_fresnel();
    test_hg_mean();
    test_transport_determinism_and_energy();
    test_beer_lambert();
    test_gaussian_source();
    test_ring_source_area_sampling();
    test_ring_uniform_azimuth_and_per_sample_aim();
    test_rotated_detector_and_exterior_na();
    test_detector_filter_monotonicity_and_invariance();
    test_ideal_detector_and_detected_path_statistics();
    test_detector_thread_determinism();
    test_ring_transport();
    return 0;
}

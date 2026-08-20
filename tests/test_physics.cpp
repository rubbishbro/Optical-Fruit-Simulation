#include "fruitsim/geometry/layered_sphere.hpp"
#include "fruitsim/optics/optics.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"

#include <cassert>
#include <cmath>

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
    const auto entry = sphere.first_entry({{0, 0, -12}, {0, 0, 1}});
    assert(entry);
    assert(close(entry->distance_mm, 2.0));
    assert(entry->to_region == 2);
    const auto next = sphere.next_boundary({{0, 0, -9.9}, {0, 0, 1}}, 2);
    assert(next);
    assert(next->to_region == 1);
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

} // namespace

int main()
{
    test_geometry();
    test_fresnel();
    test_hg_mean();
    test_transport_determinism_and_energy();
    test_beer_lambert();
    test_gaussian_source();
    return 0;
}

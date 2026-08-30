#include "fruitsim/cuda/cuda_backend.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <numeric>

namespace {

fruitsim::SimulationProblem comparison_problem()
{
    fruitsim::SimulationProblem problem{
        fruitsim::LayeredSphere{{0, 0, 0},
            {{"core", 3.0}, {"flesh", 9.0}, {"skin", 10.0}}},
    };
    problem.source.position_mm = {0, 0, -12};
    problem.source.direction = {0, 0, 1};
    problem.source.type = "ring";
    problem.source.ring_plane_normal = {0, 0, 1};
    problem.source.ring_radius_mm = 3.0;
    problem.source.ring_width_mm = 1.0;
    problem.source.direction_mode = "aim_at";
    problem.source.target_mm = {0, 0, 0};
    problem.source.spatial_sampling = "uniform_area";
    problem.detector.enabled = true;
    problem.detector.center_mm = {0, 0, -10.1};
    problem.detector.axis = {0, 0, 1};
    problem.detector.radius_mm = 4.0;
    problem.detector.acceptance_half_angle_deg = 80.0;
    problem.exterior_refractive_index = 1.0;
    problem.spectra = {{800.0, {
        {0.03, 0.8, 0.7, 1.0},
        {0.02, 1.0, 0.8, 1.0},
        {0.04, 1.2, 0.8, 1.0},
    }}};
    problem.execution.photons_per_wavelength = 12000;
    problem.execution.batch_size = 1000;
    problem.execution.max_reduction_batches = 64;
    problem.execution.seed = 8675309;
    problem.execution.threads = 4;
    problem.execution.roulette_threshold = 1.0e-4;
    problem.execution.max_events = 10000;
    problem.scoring.radial_bins = 10;
    problem.scoring.radial_max_mm = 10.0;
    problem.scoring.depth_bins = 20;
    return problem;
}

double l1_distance(const std::vector<double>& left, const std::vector<double>& right)
{
    assert(left.size() == right.size());
    double value = 0.0;
    for (std::size_t index = 0; index < left.size(); ++index) {
        value += std::abs(left[index] - right[index]);
    }
    return value;
}

void assert_energy(const fruitsim::WavelengthResult& result)
{
    assert(std::abs(result.energy_residual) < 5.0e-5);
    const double absorbed = std::accumulate(
        result.absorbed_by_region.begin(), result.absorbed_by_region.end(), 0.0);
    assert(std::abs(1.0 - result.reflectance - result.transmittance
        - absorbed - result.discarded_weight) < 5.0e-5);
}

} // namespace

int main()
{
    if (fruitsim::enumerate_cuda_devices().empty()) return 77;

    const auto problem = comparison_problem();
    fruitsim::CpuTransportBackend cpu_backend;
    fruitsim::CudaTransportBackend cuda_backend;
    const auto cpu = cpu_backend.run(problem).wavelengths.front();
    const auto gpu = cuda_backend.run(problem).wavelengths.front();
    const auto gpu_repeat = cuda_backend.run(problem).wavelengths.front();

    assert_energy(cpu);
    assert_energy(gpu);
    assert(cpu.boundary_failures == 0);
    assert(cpu.max_event_terminations == 0);
    assert(gpu.boundary_failures == 0);
    assert(gpu.max_event_terminations == 0);
    assert(gpu.photons == problem.execution.photons_per_wavelength);
    assert(std::abs(cpu.reflectance - gpu.reflectance) < 0.02);
    assert(std::abs(cpu.transmittance - gpu.transmittance) < 0.02);
    assert(cpu.absorbed_by_region.size() == gpu.absorbed_by_region.size());
    for (std::size_t region = 0; region < cpu.absorbed_by_region.size(); ++region) {
        assert(std::abs(cpu.absorbed_by_region[region] - gpu.absorbed_by_region[region]) < 0.02);
    }
    assert(l1_distance(cpu.radial_reflectance, gpu.radial_reflectance) < 0.05);
    assert(std::abs(cpu.penetration_q50_mm - gpu.penetration_q50_mm) <= 1.0);
    assert(std::abs(cpu.penetration_q90_mm - gpu.penetration_q90_mm) <= 2.0);
    assert(cpu.detected_weight > 0.0);
    assert(gpu.detected_weight > 0.0);
    assert(std::abs(cpu.detection_efficiency - gpu.detection_efficiency) < 0.01);
    assert(std::abs(cpu.detected_penetration_mean_mm
        - gpu.detected_penetration_mean_mm) <= 2.0);
    assert(std::abs(cpu.skin_path_fraction - gpu.skin_path_fraction) < 0.15);
    assert(std::abs(cpu.flesh_path_fraction - gpu.flesh_path_fraction) < 0.15);

    // Per-photon output followed by fixed host reduction makes scalar CUDA
    // results bitwise repeatable for a fixed device, seed and build.
    assert(gpu.reflectance == gpu_repeat.reflectance);
    assert(gpu.transmittance == gpu_repeat.transmittance);
    assert(gpu.absorbed_by_region == gpu_repeat.absorbed_by_region);
    assert(gpu.discarded_weight == gpu_repeat.discarded_weight);
    assert(gpu.radial_reflectance == gpu_repeat.radial_reflectance);
    assert(gpu.detected_photon_count == gpu_repeat.detected_photon_count);
    assert(gpu.detected_weight == gpu_repeat.detected_weight);
    assert(gpu.detected_penetration_mean_mm == gpu_repeat.detected_penetration_mean_mm);
    assert(gpu.skin_path_fraction == gpu_repeat.skin_path_fraction);
    assert(gpu.flesh_path_fraction == gpu_repeat.flesh_path_fraction);
    return 0;
}

#include "fruitsim/runtime/cpu_backend.hpp"

#include "fruitsim/transport/monte_carlo.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <mutex>
#include <numeric>
#include <thread>

namespace fruitsim {

namespace {

double standard_error(const std::vector<double>& values)
{
    if (values.size() < 2) {
        return 0.0;
    }
    const double mean = std::accumulate(values.begin(), values.end(), 0.0)
        / static_cast<double>(values.size());
    double sum_squared = 0.0;
    for (const double value : values) {
        const double delta = value - mean;
        sum_squared += delta * delta;
    }
    return std::sqrt(
        sum_squared / static_cast<double>(values.size() - 1)
        / static_cast<double>(values.size()));
}

double histogram_quantile(
    const std::vector<std::uint64_t>& histogram, double quantile, double max_depth)
{
    const auto total = std::accumulate(
        histogram.begin(), histogram.end(), std::uint64_t{0});
    if (total == 0) {
        return 0.0;
    }
    const std::uint64_t target = static_cast<std::uint64_t>(
        std::ceil(quantile * static_cast<double>(total)));
    std::uint64_t cumulative = 0;
    for (std::size_t index = 0; index < histogram.size(); ++index) {
        cumulative += histogram[index];
        if (cumulative >= target) {
            return (static_cast<double>(index) + 0.5)
                / static_cast<double>(histogram.size()) * max_depth;
        }
    }
    return max_depth;
}

} // namespace

SimulationResult CpuTransportBackend::run(
    const SimulationProblem& problem, const ProgressSink& progress,
    const std::atomic_bool* cancel) const
{
    problem.validate();
    const auto started = std::chrono::steady_clock::now();
    SimulationResult output;
    output.backend = name();

    const std::size_t requested_threads = problem.execution.threads == 0
        ? std::max(1U, std::thread::hardware_concurrency())
        : problem.execution.threads;
    output.runtime_metadata = {
        {"state_precision", "double"},
        {"tally_precision", "double"},
        {"reduction", "fixed_batch_order"},
        {"worker_threads", std::to_string(requested_threads)},
    };

    for (std::size_t wavelength_index = 0;
         wavelength_index < problem.spectra.size(); ++wavelength_index) {
        const std::uint64_t total = problem.execution.photons_per_wavelength;
        const std::uint64_t batch_size = problem.execution.batch_size;
        const std::size_t requested_batches = static_cast<std::size_t>(
            (total + batch_size - 1) / batch_size);
        const std::size_t batch_count = std::min(
            requested_batches, problem.execution.max_reduction_batches);
        std::vector<BatchResult> batches(batch_count);
        std::atomic_size_t next_batch{0};
        std::atomic_uint64_t completed{0};
        std::mutex progress_mutex;

        const auto worker = [&]() {
            while (true) {
                if (cancel && cancel->load()) {
                    break;
                }
                const std::size_t batch_index = next_batch.fetch_add(1);
                if (batch_index >= batch_count) {
                    break;
                }
                const std::uint64_t first = total * batch_index / batch_count;
                const std::uint64_t end = total * (batch_index + 1) / batch_count;
                const std::uint64_t count = end - first;
                batches[batch_index] = simulate_batch(
                    problem, wavelength_index, first, count);
                const std::uint64_t done = completed.fetch_add(count) + count;
                if (progress) {
                    std::lock_guard<std::mutex> lock(progress_mutex);
                    progress({wavelength_index, done, total});
                }
            }
        };

        const std::size_t thread_count = std::min(requested_threads, batch_count);
        std::vector<std::thread> workers;
        workers.reserve(thread_count);
        for (std::size_t index = 0; index < thread_count; ++index) {
            workers.emplace_back(worker);
        }
        for (auto& thread : workers) {
            thread.join();
        }

        WavelengthResult result;
        result.wavelength_nm = problem.spectra[wavelength_index].wavelength_nm;
        result.absorbed_by_region.assign(problem.domain.layers().size(), 0.0);
        result.radial_reflectance.assign(problem.scoring.radial_bins, 0.0);
        if (problem.scoring.grid_size > 0) {
            const std::size_t size = problem.scoring.grid_size;
            result.absorption_grid.assign(size * size * size, 0.0);
        }
        std::vector<std::uint64_t> depth_histogram(problem.scoring.depth_bins, 0);
        std::vector<double> batch_reflectance;
        std::vector<double> batch_transmittance;

        for (const auto& batch : batches) {
            if (batch.photon_count == 0) {
                continue;
            }
            result.photons += batch.photon_count;
            result.reflectance += batch.reflected;
            result.transmittance += batch.transmitted;
            result.discarded_weight += batch.discarded;
            result.boundary_failures += batch.boundary_failures;
            result.max_event_terminations += batch.max_event_terminations;
            batch_reflectance.push_back(batch.reflected / batch.photon_count);
            batch_transmittance.push_back(batch.transmitted / batch.photon_count);
            for (std::size_t index = 0; index < result.absorbed_by_region.size(); ++index) {
                result.absorbed_by_region[index] += batch.absorbed[index];
            }
            for (std::size_t index = 0; index < result.radial_reflectance.size(); ++index) {
                result.radial_reflectance[index] += batch.radial_reflectance[index];
            }
            for (std::size_t index = 0; index < result.absorption_grid.size(); ++index) {
                result.absorption_grid[index] += batch.absorption_grid[index];
            }
            for (std::size_t index = 0; index < depth_histogram.size(); ++index) {
                depth_histogram[index] += batch.depth_histogram[index];
            }
            result.trajectories.insert(
                result.trajectories.end(), batch.trajectories.begin(), batch.trajectories.end());
        }

        if (result.photons > 0) {
            const double scale = 1.0 / static_cast<double>(result.photons);
            result.reflectance *= scale;
            result.transmittance *= scale;
            result.discarded_weight *= scale;
            for (double& value : result.absorbed_by_region) value *= scale;
            for (double& value : result.radial_reflectance) value *= scale;
            for (double& value : result.absorption_grid) value *= scale;
        }
        result.reflectance_standard_error = standard_error(batch_reflectance);
        result.transmittance_standard_error = standard_error(batch_transmittance);
        const double absorbed = std::accumulate(
            result.absorbed_by_region.begin(), result.absorbed_by_region.end(), 0.0);
        result.energy_residual = 1.0 - result.reflectance - result.transmittance
            - absorbed - result.discarded_weight;
        const double max_depth = 2.0 * problem.domain.outer_radius_mm();
        result.penetration_q50_mm = histogram_quantile(depth_histogram, 0.5, max_depth);
        result.penetration_q90_mm = histogram_quantile(depth_histogram, 0.9, max_depth);
        output.wavelengths.push_back(std::move(result));

        if (cancel && cancel->load()) {
            break;
        }
    }

    output.elapsed_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    return output;
}

} // namespace fruitsim

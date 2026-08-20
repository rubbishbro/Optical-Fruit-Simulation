#include "fruitsim/io/result_writer.hpp"

#include <fstream>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <numeric>
#include <stdexcept>

namespace fruitsim {

namespace {

std::ofstream output_file(const std::filesystem::path& path)
{
    std::ofstream stream(path);
    if (!stream) {
        throw std::runtime_error("Cannot create output file: " + path.string());
    }
    stream << std::setprecision(12);
    return stream;
}

} // namespace

void write_simulation_results(
    const SimulationProblem& problem, const SimulationResult& result,
    const std::filesystem::path& output_directory)
{
    std::filesystem::create_directories(output_directory);

    auto summary = output_file(output_directory / "summary.csv");
    summary << "wavelength_nm,photons,reflectance,reflectance_se,transmittance,"
               "transmittance_se,absorbed_total,discarded_weight,energy_residual,"
               "penetration_q50_mm,penetration_q90_mm";
    for (const auto& layer : problem.domain.layers()) summary << ",absorbed_" << layer.name;
    summary << '\n';
    for (const auto& wavelength : result.wavelengths) {
        const double absorbed = std::accumulate(
            wavelength.absorbed_by_region.begin(), wavelength.absorbed_by_region.end(), 0.0);
        summary << wavelength.wavelength_nm << ',' << wavelength.photons << ','
                << wavelength.reflectance << ',' << wavelength.reflectance_standard_error << ','
                << wavelength.transmittance << ',' << wavelength.transmittance_standard_error << ','
                << absorbed << ',' << wavelength.discarded_weight << ','
                << wavelength.energy_residual << ',' << wavelength.penetration_q50_mm << ','
                << wavelength.penetration_q90_mm;
        for (double value : wavelength.absorbed_by_region) summary << ',' << value;
        summary << '\n';
    }

    auto detectors = output_file(output_directory / "detectors.csv");
    detectors << "wavelength_nm,detector,bin_index,r_min_mm,r_max_mm,value\n";
    for (const auto& wavelength : result.wavelengths) {
        for (std::size_t index = 0; index < wavelength.radial_reflectance.size(); ++index) {
            const double width = problem.scoring.radial_max_mm
                / static_cast<double>(problem.scoring.radial_bins);
            detectors << wavelength.wavelength_nm << ",reflectance_radial," << index << ','
                      << index * width << ',' << (index + 1) * width << ','
                      << wavelength.radial_reflectance[index] << '\n';
        }
    }

    if (problem.scoring.grid_size > 0) {
        auto grid = output_file(output_directory / "absorption_grid.csv");
        grid << "wavelength_nm,x_index,y_index,z_index,absorbed_weight\n";
        const std::size_t size = problem.scoring.grid_size;
        for (const auto& wavelength : result.wavelengths) {
            for (std::size_t z = 0; z < size; ++z) {
                for (std::size_t y = 0; y < size; ++y) {
                    for (std::size_t x = 0; x < size; ++x) {
                        const std::size_t index = (z * size + y) * size + x;
                        const double value = wavelength.absorption_grid[index];
                        if (value != 0.0) {
                            grid << wavelength.wavelength_nm << ',' << x << ',' << y << ','
                                 << z << ',' << value << '\n';
                        }
                    }
                }
            }
        }
    }

    if (problem.scoring.trajectory_limit > 0) {
        auto trajectories = output_file(output_directory / "trajectories.csv");
        trajectories << "wavelength_nm,photon_id,event,x_mm,y_mm,z_mm,weight,region\n";
        for (const auto& wavelength : result.wavelengths) {
            for (const auto& point : wavelength.trajectories) {
                trajectories << wavelength.wavelength_nm << ',' << point.photon_id << ','
                             << point.event << ',' << point.position_mm.x() << ','
                             << point.position_mm.y() << ',' << point.position_mm.z() << ','
                             << point.weight << ',' << point.region << '\n';
            }
        }
    }

    nlohmann::json manifest{
        {"schema_version", 1},
        {"software", "fruitsim"},
        {"software_version", "0.2.0"},
        {"session_id", problem.metadata.session_id},
        {"cultivar", problem.metadata.cultivar},
        {"dataset_id", problem.metadata.dataset_id},
        {"source_type", problem.metadata.source_type},
        {"transport_mode", problem.metadata.transport_mode},
        {"assumptions", problem.metadata.assumptions},
        {"backend", result.backend},
        {"seed", problem.execution.seed},
        {"threads", problem.execution.threads},
        {"photons_per_wavelength", problem.execution.photons_per_wavelength},
        {"elapsed_seconds", result.elapsed_seconds},
        {"synthetic_warning",
         problem.metadata.source_type == "synthetic"
             ? "METHOD DEMONSTRATION ONLY - NOT VALID FOR REAL APPLE SSC PREDICTION"
             : ""},
    };
    auto manifest_stream = output_file(output_directory / "manifest.json");
    manifest_stream << manifest.dump(2) << '\n';
}

} // namespace fruitsim

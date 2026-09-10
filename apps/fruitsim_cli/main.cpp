#include "fruitsim/io/config_loader.hpp"
#include "fruitsim/io/result_writer.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"
#ifdef FRUITSIM_HAS_CUDA
#include "fruitsim/cuda/cuda_backend.hpp"
#endif

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Arguments {
    std::string command;
    std::filesystem::path config;
    std::filesystem::path output = "results/fruitsim";
    std::uint64_t photons = 0;
    std::uint64_t seed = 0;
    std::size_t threads = 0;
    std::string backend;
    std::vector<double> ring_radii_mm;
};

void usage()
{
    std::cout
        << "fruitsim_cli run --config FILE [--output DIR] [--photons N] [--seed N] "
           "[--threads N] [--backend cpu|cuda]\n"
        << "fruitsim_cli scan-ring --config FILE --ring-radii 1,2,3,5,8,10,12,15 "
           "[--output DIR] [--photons N] [--backend cpu|cuda]\n"
        << "fruitsim_cli validate --config FILE\n"
        << "fruitsim_cli devices\n";
}

Arguments parse_arguments(int argc, char** argv)
{
    if (argc < 2) throw std::invalid_argument("Missing command");
    Arguments args;
    args.command = argv[1];
    for (int index = 2; index < argc; ++index) {
        const std::string option = argv[index];
        const auto value = [&]() -> std::string {
            if (++index >= argc) throw std::invalid_argument("Missing value for " + option);
            return argv[index];
        };
        if (option == "--config") args.config = value();
        else if (option == "--output") args.output = value();
        else if (option == "--photons") args.photons = std::stoull(value());
        else if (option == "--seed") args.seed = std::stoull(value());
        else if (option == "--threads") args.threads = std::stoull(value());
        else if (option == "--backend") args.backend = value();
        else if (option == "--ring-radii") {
            std::stringstream values(value());
            std::string item;
            while (std::getline(values, item, ',')) {
                const double radius = std::stod(item);
                if (radius <= 0.0) {
                    throw std::invalid_argument("Ring radii must be positive");
                }
                args.ring_radii_mm.push_back(radius);
            }
        }
        else throw std::invalid_argument("Unknown option: " + option);
    }
    return args;
}

std::unique_ptr<fruitsim::ITransportBackend> make_backend(const std::string& name)
{
    if (name == "cpu") return std::make_unique<fruitsim::CpuTransportBackend>();
#ifdef FRUITSIM_HAS_CUDA
    if (name == "cuda") return std::make_unique<fruitsim::CudaTransportBackend>();
#endif
    throw std::invalid_argument("Requested backend is unavailable: " + name);
}

} // namespace

int main(int argc, char** argv)
{
    try {
        const Arguments args = parse_arguments(argc, argv);
        if (args.command == "devices") {
            std::cout << "cpu: available\n";
#ifdef FRUITSIM_HAS_CUDA
            const auto devices = fruitsim::enumerate_cuda_devices();
            if (devices.empty()) std::cout << "cuda: built, no device available\n";
            for (const auto& device : devices) {
                std::cout << "cuda:" << device.index << ": " << device.name << " (compute "
                          << device.compute_major << '.' << device.compute_minor << ")\n";
            }
#else
            std::cout << "cuda: not built (configure FRUITSIM_ENABLE_CUDA=ON)\n";
#endif
            return 0;
        }
        if (args.config.empty()) throw std::invalid_argument("--config is required");
        if (args.command == "validate") {
            fruitsim::validate_simulation_config(args.config);
            std::cout << "configuration is valid: " << args.config << '\n';
            return 0;
        }
        if (args.command != "run" && args.command != "scan-ring") {
            usage();
            throw std::invalid_argument("Unknown command: " + args.command);
        }

        auto problem = fruitsim::load_simulation_config(args.config);
        if (args.photons > 0) problem.execution.photons_per_wavelength = args.photons;
        if (args.seed > 0) problem.execution.seed = args.seed;
        if (args.threads > 0) problem.execution.threads = args.threads;
        if (!args.backend.empty()) problem.execution.backend = args.backend;
        auto backend = make_backend(problem.execution.backend);
        if (args.command == "scan-ring") {
            if (problem.source.type != "ring") {
                throw std::invalid_argument("scan-ring requires source.type=ring");
            }
            if (args.ring_radii_mm.empty()) {
                throw std::invalid_argument("scan-ring requires --ring-radii");
            }
            std::filesystem::create_directories(args.output);
            std::ofstream scan(args.output / "ring_scan.csv");
            if (!scan) throw std::runtime_error("Cannot create ring_scan.csv");
            scan << std::setprecision(12)
                 << "ring_radius_mm,wavelength_nm,launched_photons,detected_photon_count,"
                    "detected_weight,detection_efficiency,detected_reflectance,"
                    "detected_specular_weight,detected_diffuse_weight,"
                    "detected_penetration_mean_mm,detected_penetration_median_mm,"
                    "weighted_mean_total_path_mm,weighted_mean_skin_path_mm,"
                    "weighted_mean_flesh_path_mm,skin_path_fraction,flesh_path_fraction";
            for (const auto& layer : problem.domain.layers()) {
                scan << ",weighted_mean_path_" << layer.name
                     << "_mm,path_fraction_" << layer.name;
            }
            scan << '\n';
            for (const double radius : args.ring_radii_mm) {
                problem.source.ring_radius_mm = radius;
                problem.validate();
                const auto scan_result = backend->run(problem);
                for (const auto& wavelength : scan_result.wavelengths) {
                    scan << radius << ',' << wavelength.wavelength_nm << ','
                         << wavelength.photons << ',' << wavelength.detected_photon_count << ','
                         << wavelength.detected_weight << ',' << wavelength.detection_efficiency
                         << ',' << wavelength.detected_reflectance << ','
                         << wavelength.detected_specular_weight << ','
                         << wavelength.detected_diffuse_weight << ','
                         << wavelength.detected_penetration_mean_mm << ','
                         << wavelength.detected_penetration_median_mm << ','
                         << wavelength.weighted_mean_total_path_mm << ','
                         << wavelength.weighted_mean_skin_path_mm << ','
                         << wavelength.weighted_mean_flesh_path_mm << ','
                         << wavelength.skin_path_fraction << ','
                         << wavelength.flesh_path_fraction;
                    for (std::size_t region = 0;
                         region < wavelength.weighted_mean_path_by_region_mm.size(); ++region) {
                        scan << ',' << wavelength.weighted_mean_path_by_region_mm[region]
                             << ',' << wavelength.path_fraction_by_region[region];
                    }
                    scan << '\n';
                }
                std::cerr << "completed ring radius " << radius << " mm\n";
            }
            nlohmann::json scan_manifest{
                {"schema_version", 1},
                {"software", "fruitsim"},
                {"software_version", "0.5.0"},
                {"config", args.config.string()},
                {"backend", problem.execution.backend},
                {"seed", problem.execution.seed},
                {"photons_per_wavelength", problem.execution.photons_per_wavelength},
                {"ring_radii_mm", args.ring_radii_mm},
                {"instrument_assumption_status", "simulation_demo_assumption"},
                {"assumptions", problem.metadata.assumptions},
                {"metric_definition",
                 "detection_efficiency = detected_weight / launched_photons"},
            };
            std::ofstream manifest(args.output / "ring_scan_manifest.json");
            if (!manifest) throw std::runtime_error("Cannot create ring_scan_manifest.json");
            manifest << scan_manifest.dump(2) << '\n';
            std::cout << "ring scan results: " << args.output / "ring_scan.csv" << '\n';
            return 0;
        }
        std::size_t last_decile = 101;
        const auto result = backend->run(problem, [&](const fruitsim::ProgressUpdate& update) {
            const std::size_t percent = static_cast<std::size_t>(
                100 * update.completed_photons / update.total_photons);
            if (percent / 10 != last_decile) {
                std::cerr << "wavelength " << problem.spectra[update.wavelength_index].wavelength_nm
                          << " nm: " << percent << "%\n";
                last_decile = percent / 10;
            }
        });
        fruitsim::write_simulation_results(problem, result, args.output);
        const std::uint64_t total_photons = std::accumulate(result.wavelengths.begin(),
            result.wavelengths.end(), std::uint64_t{0},
            [](std::uint64_t total, const fruitsim::WavelengthResult& wavelength) {
                return total + wavelength.photons;
            });
        const double rate = result.elapsed_seconds > 0.0
            ? static_cast<double>(total_photons) / result.elapsed_seconds : 0.0;
        std::cout << "completed " << result.wavelengths.size() << " wavelength(s) in "
                  << result.elapsed_seconds << " s (" << total_photons << " photons, "
                  << rate << " photons/s)\nresults: " << args.output << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fruitsim_cli: " << error.what() << '\n';
        usage();
        return 1;
    }
}

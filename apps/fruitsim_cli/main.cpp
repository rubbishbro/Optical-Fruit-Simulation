#include "fruitsim/io/config_loader.hpp"
#include "fruitsim/io/result_writer.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"
#ifdef FRUITSIM_HAS_CUDA
#include "fruitsim/cuda/cuda_backend.hpp"
#endif

#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

struct Arguments {
    std::string command;
    std::filesystem::path config;
    std::filesystem::path output = "results/fruitsim";
    std::uint64_t photons = 0;
    std::uint64_t seed = 0;
    std::size_t threads = 0;
    std::string backend;
};

void usage()
{
    std::cout
        << "fruitsim_cli run --config FILE [--output DIR] [--photons N] [--seed N] "
           "[--threads N] [--backend cpu|cuda]\n"
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
        else throw std::invalid_argument("Unknown option: " + option);
    }
    return args;
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
        if (args.command != "run") {
            usage();
            throw std::invalid_argument("Unknown command: " + args.command);
        }

        auto problem = fruitsim::load_simulation_config(args.config);
        if (args.photons > 0) problem.execution.photons_per_wavelength = args.photons;
        if (args.seed > 0) problem.execution.seed = args.seed;
        if (args.threads > 0) problem.execution.threads = args.threads;
        if (!args.backend.empty()) problem.execution.backend = args.backend;
        std::unique_ptr<fruitsim::ITransportBackend> backend;
        if (problem.execution.backend == "cpu") {
            backend = std::make_unique<fruitsim::CpuTransportBackend>();
#ifdef FRUITSIM_HAS_CUDA
        } else if (problem.execution.backend == "cuda") {
            backend = std::make_unique<fruitsim::CudaTransportBackend>();
#endif
        } else {
            throw std::invalid_argument("Requested backend is unavailable: " + problem.execution.backend);
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
        std::cout << "completed " << result.wavelengths.size() << " wavelength(s) in "
                  << result.elapsed_seconds << " s\nresults: " << args.output << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fruitsim_cli: " << error.what() << '\n';
        usage();
        return 1;
    }
}

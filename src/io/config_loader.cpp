#include "fruitsim/io/config_loader.hpp"

#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace fruitsim {

namespace {

using Json = nlohmann::json;

Vec3 read_vec3(const Json& value, const char* field)
{
    if (!value.is_array() || value.size() != 3) {
        throw std::invalid_argument(std::string(field) + " must be a three-element array");
    }
    return {value[0].get<double>(), value[1].get<double>(), value[2].get<double>()};
}

OpticalProperties read_properties(const Json& value, const std::string& context)
{
    OpticalProperties properties;
    properties.mu_a_mm_inv = value.at("mu_a_mm_inv").get<double>();
    properties.g = value.at("g").get<double>();
    properties.refractive_index = value.at("refractive_index").get<double>();
    const bool has_mu_s = value.contains("mu_s_mm_inv");
    const bool has_mu_s_prime = value.contains("mu_s_prime_mm_inv");
    if (has_mu_s == has_mu_s_prime) {
        throw std::invalid_argument(
            context + ": specify exactly one of mu_s_mm_inv and mu_s_prime_mm_inv");
    }
    properties.mu_s_mm_inv = has_mu_s
        ? value.at("mu_s_mm_inv").get<double>()
        : value.at("mu_s_prime_mm_inv").get<double>() / (1.0 - properties.g);
    properties.validate(context);
    return properties;
}

} // namespace

SimulationProblem load_simulation_config(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    if (!stream) {
        throw std::runtime_error("Cannot open simulation config: " + path.string());
    }
    Json root;
    stream >> root;
    if (root.value("schema_version", 0) != 1) {
        throw std::invalid_argument("Unsupported or missing schema_version; expected 1");
    }

    const auto& domain_json = root.at("domain");
    if (domain_json.value("type", std::string{}) != "layered_sphere") {
        throw std::invalid_argument("Only domain.type=layered_sphere is currently supported");
    }
    std::vector<SphereLayer> layers;
    for (const auto& layer : domain_json.at("layers_inner_to_outer")) {
        layers.push_back({
            layer.at("name").get<std::string>(),
            layer.at("outer_radius_mm").get<double>(),
        });
    }

    SimulationProblem problem{
        LayeredSphere{
            read_vec3(domain_json.value("center_mm", Json::array({0.0, 0.0, 0.0})),
                "domain.center_mm"),
            std::move(layers),
        },
    };
    problem.exterior_refractive_index = domain_json.value("exterior_refractive_index", 1.0);

    const auto& session = root.at("session");
    problem.metadata.session_id = session.value("id", std::string{"fruitsim"});
    problem.metadata.cultivar = session.value("cultivar", std::string{"unknown"});
    problem.metadata.dataset_id = session.value("dataset_id", std::string{"unknown"});
    problem.metadata.source_type = session.value("source_type", std::string{"unknown"});
    problem.metadata.transport_mode = session.value("transport_mode", std::string{"scalar"});
    problem.metadata.assumptions = session.value("assumptions", std::vector<std::string>{});
    problem.execution.photons_per_wavelength = session.at("photons_per_wavelength").get<std::uint64_t>();
    problem.execution.seed = session.value("seed", std::uint64_t{20260819});
    problem.execution.threads = session.value("threads", std::size_t{0});
    problem.execution.backend = session.value("backend", std::string{"cpu"});
    problem.execution.batch_size = session.value("batch_size", std::size_t{1024});
    problem.execution.max_reduction_batches = session.value(
        "max_reduction_batches", std::size_t{256});
    problem.execution.max_events = session.value("max_events", std::uint32_t{100000});

    if (root.contains("roulette")) {
        const auto& roulette = root.at("roulette");
        problem.execution.roulette_threshold = roulette.value("threshold", 1.0e-4);
        problem.execution.roulette_survival = roulette.value("survival_probability", 0.1);
    }

    const auto& source = root.at("source");
    problem.source.type = source.value("type", std::string{});
    if (problem.source.type != "pencil" && problem.source.type != "gaussian") {
        throw std::invalid_argument("source.type must be pencil or gaussian");
    }
    problem.source.position_mm = read_vec3(source.at("position_mm"), "source.position_mm");
    problem.source.direction = read_vec3(source.at("direction"), "source.direction").normalize();
    problem.source.gaussian_sigma_mm = source.value("sigma_mm", 0.0);

    const auto& scoring = root.value("scoring", Json::object());
    problem.scoring.radial_bins = scoring.value("radial_bins", std::size_t{32});
    problem.scoring.radial_max_mm = scoring.value(
        "radial_max_mm", problem.domain.outer_radius_mm());
    problem.scoring.grid_size = scoring.value("grid_size", std::size_t{0});
    problem.scoring.depth_bins = scoring.value("depth_bins", std::size_t{64});
    problem.scoring.trajectory_limit = scoring.value("trajectory_limit", std::size_t{0});

    for (const auto& spectral : root.at("spectra")) {
        SpectralMedium medium;
        medium.wavelength_nm = spectral.at("wavelength_nm").get<double>();
        const auto& regions = spectral.at("regions");
        for (const auto& layer : problem.domain.layers()) {
            medium.regions.push_back(read_properties(
                regions.at(layer.name), layer.name + " at "
                    + std::to_string(medium.wavelength_nm) + " nm"));
        }
        problem.spectra.push_back(std::move(medium));
    }

    problem.validate();
    return problem;
}

void validate_simulation_config(const std::filesystem::path& path)
{
    (void)load_simulation_config(path);
}

} // namespace fruitsim

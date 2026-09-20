#include "fruitsim/io/config_loader.hpp"
#include "fruitsim/io/statistical_shape_loader.hpp"
#include "fruitsim/transport/monte_carlo.hpp"
#include "fruitsim/geometry/mesh_geometry.hpp"

#include <algorithm>
#include <fstream>
#include <memory>
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
    const std::string domain_type = domain_json.value("type", std::string{});
    if (domain_type != "layered_sphere" && domain_type != "statistical_mesh") {
        throw std::invalid_argument(
            "domain.type must be layered_sphere or statistical_mesh");
    }
    std::vector<SphereLayer> layers;
    const auto& layer_json = domain_json.at("layers_inner_to_outer");
    for (const auto& layer : layer_json) {
        layers.push_back({layer.at("name").get<std::string>(),
            layer.value("outer_radius_mm", 1.0)});
    }
    if (layers.empty() || (domain_type == "statistical_mesh" && layers.size() != 2)) {
        throw std::invalid_argument("statistical_mesh currently requires flesh and skin layers");
    }
    std::shared_ptr<MeshGeometry> mesh_geometry;
    const Vec3 center = read_vec3(
        domain_json.value("center_mm", Json::array({0.0, 0.0, 0.0})), "domain.center_mm");
    if (domain_type == "statistical_mesh") {
        std::filesystem::path model_path = domain_json.at("model").get<std::string>();
        if (model_path.is_relative()) model_path = path.parent_path() / model_path;
        const auto shape = load_statistical_fuji_shape(model_path);
        const auto outer = shape.sample_random(
            domain_json.value("shape_seed", std::uint64_t{42}),
            domain_json.value("shape_sample_id", std::uint64_t{0}),
            domain_json.value("active_modes", std::size_t{0}),
            domain_json.value("sigma_clip", 3.0));
        const double skin_thickness = domain_json.value("skin_thickness_mm", 1.0);
        if (skin_thickness <= 0.0) {
            throw std::invalid_argument("domain.skin_thickness_mm must be positive");
        }
        StatisticalShapeMesh inner = outer;
        for (std::size_t index = 0; index < outer.vertices_mm.size(); ++index) {
            const Vec3 offset = outer.vertices_mm[index] - center;
            const double radius = offset.norm();
            if (radius <= skin_thickness) {
                throw std::invalid_argument("skin thickness exceeds sampled mesh radius");
            }
            inner.vertices_mm[index] = center
                + offset * ((radius - skin_thickness) / radius);
        }
        double maximum_radius = 0.0;
        for (const auto& vertex : outer.vertices_mm) {
            maximum_radius = std::max(maximum_radius, (vertex - center).norm());
        }
        layers[0].outer_radius_mm = std::max(0.1, maximum_radius - skin_thickness);
        layers[1].outer_radius_mm = maximum_radius;
        mesh_geometry = std::make_shared<MeshGeometry>(outer, std::move(inner), center);
    }

    SimulationProblem problem{
        LayeredSphere{center, std::move(layers)}, mesh_geometry,
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
    problem.execution.boundary_epsilon_mm = session.value("boundary_epsilon_mm", 1.0e-7);

    if (root.contains("roulette")) {
        const auto& roulette = root.at("roulette");
        problem.execution.roulette_threshold = roulette.value("threshold", 1.0e-4);
        problem.execution.roulette_survival = roulette.value("survival_probability", 0.1);
    }

    const auto& source = root.at("source");
    problem.source.type = source.value("type", std::string{});
    if (problem.source.type != "pencil" && problem.source.type != "gaussian"
        && problem.source.type != "ring") {
        throw std::invalid_argument("source.type must be pencil, gaussian, or ring");
    }
    if (problem.source.type == "ring") {
        problem.source.position_mm = read_vec3(source.at("center_mm"), "source.center_mm");
        problem.source.ring_plane_normal = read_vec3(
            source.at("plane_normal"), "source.plane_normal").normalize();
        problem.source.ring_radius_mm = source.at("ring_radius_mm").get<double>();
        problem.source.ring_width_mm = source.value("ring_width_mm", 0.0);
        problem.source.direction_mode = source.value("direction_mode", std::string{"fixed"});
        problem.source.spatial_sampling = source.value(
            "spatial_sampling",
            problem.source.ring_width_mm > 0.0 ? std::string{"uniform_area"}
                                               : std::string{"uniform_azimuth"});
        if (problem.source.direction_mode == "aim_at") {
            problem.source.target_mm = read_vec3(
                source.value("target_mm", Json::array({
                    problem.domain.center().x(), problem.domain.center().y(),
                    problem.domain.center().z()})),
                "source.target_mm");
            problem.source.direction = (problem.source.target_mm
                - problem.source.position_mm).normalize();
        } else {
            problem.source.direction = read_vec3(
                source.at("direction"), "source.direction").normalize();
        }
    } else {
        problem.source.position_mm = read_vec3(source.at("position_mm"), "source.position_mm");
        problem.source.direction = read_vec3(source.at("direction"), "source.direction").normalize();
        problem.source.gaussian_sigma_mm = source.value("sigma_mm", 0.0);
    }

    if (root.contains("instrument")) {
        const auto& instrument = root.at("instrument");
        if (instrument.contains("detector")) {
            const auto& detector = instrument.at("detector");
            problem.detector.enabled = detector.value("enabled", true);
            problem.detector.type = detector.value("type", std::string{"circular"});
            problem.detector.center_mm = read_vec3(
                detector.at("center_mm"), "instrument.detector.center_mm");
            problem.detector.axis = read_vec3(
                detector.at("axis"), "instrument.detector.axis").normalize();
            problem.detector.radius_mm = detector.at("radius_mm").get<double>();
            const bool has_na = detector.contains("numerical_aperture");
            const bool has_angle = detector.contains("acceptance_half_angle_deg");
            if (has_na && has_angle) {
                throw std::invalid_argument(
                    "Detector must specify only one of numerical_aperture and "
                    "acceptance_half_angle_deg");
            }
            if (has_na) {
                problem.detector.numerical_aperture =
                    detector.at("numerical_aperture").get<double>();
                problem.detector.acceptance_half_angle_deg =
                    detector_acceptance_half_angle_degrees(
                        problem.detector.numerical_aperture,
                        problem.exterior_refractive_index);
            } else {
                problem.detector.acceptance_half_angle_deg = detector.value(
                    "acceptance_half_angle_deg", 90.0);
            }
        }
    }

    const auto& scoring = root.value("scoring", Json::object());
    problem.scoring.radial_bins = scoring.value("radial_bins", std::size_t{32});
    problem.scoring.radial_max_mm = scoring.value(
        "radial_max_mm", problem.domain.outer_radius_mm());
    problem.scoring.grid_size = scoring.value("grid_size", std::size_t{0});
    problem.scoring.depth_bins = scoring.value("depth_bins", std::size_t{64});
    problem.scoring.trajectory_limit = scoring.value("trajectory_limit", std::size_t{0});
    problem.scoring.detector_trajectory_limit = scoring.value(
        "detector_trajectory_limit", std::size_t{0});
    problem.scoring.trajectory_mode = scoring.value(
        "trajectory_mode", std::string{"all"});

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

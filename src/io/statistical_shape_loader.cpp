#include "fruitsim/io/statistical_shape_loader.hpp"

#include <array>
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <vector>

namespace fruitsim {

StatisticalFujiShape load_statistical_fuji_shape(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("Cannot open statistical shape: " + path.string());
    nlohmann::json document;
    stream >> document;
    if (document.value("schema_version", 0) != 1
        || document.value("geometry_type", std::string{}) != "StatisticalFujiShape") {
        throw std::invalid_argument("Unsupported statistical shape artifact");
    }
    std::vector<Vec3> directions;
    for (const auto& value : document.at("directions")) {
        if (!value.is_array() || value.size() != 3) {
            throw std::invalid_argument("Statistical shape direction must have three values");
        }
        directions.emplace_back(
            value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
    }
    std::vector<StatisticalShapeMode> modes;
    for (const auto& value : document.at("pca_modes")) {
        modes.push_back({
            value.at("eigenvalue_mm2").get<double>(),
            value.at("explained_variance_ratio").get<double>(),
            value.at("deformation_mm").get<std::vector<double>>(),
        });
    }
    std::vector<std::array<std::size_t, 3>> faces;
    for (const auto& value : document.at("faces")) {
        if (!value.is_array() || value.size() != 3) {
            throw std::invalid_argument("Statistical shape face must have three indices");
        }
        faces.push_back({value[0].get<std::size_t>(), value[1].get<std::size_t>(),
            value[2].get<std::size_t>()});
    }
    return StatisticalFujiShape(
        std::move(directions), document.at("mean_radius_mm").get<std::vector<double>>(),
        std::move(modes), std::move(faces),
        document.at("cultivar_status").get<std::string>(),
        document.at("provenance").at("source_doi").get<std::string>());
}

} // namespace fruitsim

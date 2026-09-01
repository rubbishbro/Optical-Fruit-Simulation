#include "fruitsim/io/statistical_shape_loader.hpp"

#include <cassert>
#include <filesystem>

int main(int argc, char** argv)
{
    assert(argc == 2);
    const auto shape = fruitsim::load_statistical_fuji_shape(
        std::filesystem::path(argv[1]));
    assert(shape.directions().size() == 2048);
    assert(shape.faces().size() == 4092);
    assert(shape.modes().size() == 8);
    assert(shape.cultivar_status() == "unverified_in_source_record");
    assert(shape.source_doi() == "10.5281/zenodo.15635995");
    const auto first = shape.sample_random(20260901, 42, 8);
    const auto second = shape.sample_random(20260901, 42, 8);
    assert(first.vertices_mm.size() == 2048);
    for (std::size_t index = 0; index < first.vertices_mm.size(); ++index) {
        assert(first.vertices_mm[index].x() == second.vertices_mm[index].x());
        assert(first.vertices_mm[index].y() == second.vertices_mm[index].y());
        assert(first.vertices_mm[index].z() == second.vertices_mm[index].z());
    }
    return 0;
}

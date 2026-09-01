add_library(fruitsim_io
    ${PROJECT_SOURCE_DIR}/src/io/config_loader.cpp
    ${PROJECT_SOURCE_DIR}/src/io/result_writer.cpp
    ${PROJECT_SOURCE_DIR}/src/io/statistical_shape_loader.cpp
)
add_library(fruitsim::io ALIAS fruitsim_io)
target_compile_features(fruitsim_io PUBLIC cxx_std_17)
target_include_directories(fruitsim_io PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(fruitsim_io PUBLIC fruitsim::runtime nlohmann_json::nlohmann_json)
fruitsim_set_warnings(fruitsim_io)

add_executable(fruitsim_tests
    test_core.cpp
)

target_link_libraries(fruitsim_tests
    PRIVATE
        fruitsim::core
)

add_test(NAME fruitsim_tests COMMAND fruitsim_tests)

add_executable(fruitsim_physics_tests test_physics.cpp)
target_link_libraries(fruitsim_physics_tests PRIVATE fruitsim::runtime)
fruitsim_set_warnings(fruitsim_physics_tests)
add_test(NAME fruitsim_physics_tests COMMAND fruitsim_physics_tests)

add_executable(fruitsim_shape_loader_tests test_shape_loader.cpp)
target_link_libraries(fruitsim_shape_loader_tests PRIVATE fruitsim::io)
fruitsim_set_warnings(fruitsim_shape_loader_tests)
add_test(NAME fruitsim_shape_loader_tests COMMAND fruitsim_shape_loader_tests
    ${PROJECT_SOURCE_DIR}/data/shape_models/statistical_fuji_shape_zenodo_v1.json)

if(FRUITSIM_ENABLE_CUDA)
    add_executable(fruitsim_cuda_tests test_cuda.cpp)
    target_link_libraries(fruitsim_cuda_tests PRIVATE fruitsim::cuda fruitsim::runtime)
    fruitsim_set_warnings(fruitsim_cuda_tests)
    add_test(NAME fruitsim_cuda_tests COMMAND fruitsim_cuda_tests)
    set_tests_properties(fruitsim_cuda_tests PROPERTIES SKIP_RETURN_CODE 77)
endif()

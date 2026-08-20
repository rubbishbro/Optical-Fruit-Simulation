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

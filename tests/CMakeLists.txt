add_executable(fruitsim_tests
    test_core.cpp
)

target_link_libraries(fruitsim_tests
    PRIVATE
        fruitsim::core
)

add_test(NAME fruitsim_tests COMMAND fruitsim_tests)

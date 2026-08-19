add_executable(fruitsim_cli
    main.cpp
)

target_link_libraries(fruitsim_cli
    PRIVATE
        fruitsim::core
)

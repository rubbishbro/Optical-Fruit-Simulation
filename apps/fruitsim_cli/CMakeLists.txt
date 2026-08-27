add_executable(fruitsim_cli
    main.cpp
)

target_link_libraries(fruitsim_cli
    PRIVATE
        fruitsim::io
)

target_compile_features(fruitsim_cli PRIVATE cxx_std_17)
fruitsim_set_warnings(fruitsim_cli)

if(FRUITSIM_ENABLE_CUDA)
    target_link_libraries(fruitsim_cli PRIVATE fruitsim::cuda)
    target_compile_definitions(fruitsim_cli PRIVATE FRUITSIM_HAS_CUDA=1)
endif()

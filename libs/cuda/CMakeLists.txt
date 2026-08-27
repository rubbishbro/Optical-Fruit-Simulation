find_package(CUDAToolkit REQUIRED)

add_library(fruitsim_cuda cuda_backend.cu)
add_library(fruitsim::cuda ALIAS fruitsim_cuda)
target_compile_features(fruitsim_cuda PUBLIC cxx_std_17 cuda_std_17)
target_include_directories(fruitsim_cuda PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(fruitsim_cuda PUBLIC fruitsim::runtime CUDA::cudart)
set_target_properties(fruitsim_cuda PROPERTIES CUDA_SEPARABLE_COMPILATION ON)

#include "fruitsim/cuda/cuda_backend.hpp"

#include <cuda_runtime_api.h>

#include <stdexcept>

namespace fruitsim {

std::vector<CudaDeviceInfo> enumerate_cuda_devices()
{
    int count = 0;
    if (cudaGetDeviceCount(&count) != cudaSuccess) {
        return {};
    }
    std::vector<CudaDeviceInfo> devices;
    for (int index = 0; index < count; ++index) {
        cudaDeviceProp properties{};
        if (cudaGetDeviceProperties(&properties, index) == cudaSuccess) {
            devices.push_back({index, properties.name, properties.totalGlobalMem,
                properties.major, properties.minor});
        }
    }
    return devices;
}

SimulationResult CudaTransportBackend::run(
    const SimulationProblem&, const ProgressSink&, const std::atomic_bool*) const
{
    throw std::runtime_error(
        "CUDA device discovery is available, but the photon transport kernel is not yet validated");
}

} // namespace fruitsim

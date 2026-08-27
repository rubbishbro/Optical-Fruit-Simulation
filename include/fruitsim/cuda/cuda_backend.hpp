#pragma once

#include "fruitsim/transport/simulation.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace fruitsim {

struct CudaDeviceInfo {
    int index = -1;
    std::string name;
    std::size_t global_memory_bytes = 0;
    int compute_major = 0;
    int compute_minor = 0;
};

[[nodiscard]] std::vector<CudaDeviceInfo> enumerate_cuda_devices();

// CUDA scalar transport uses float photon state and double tallies. Work is
// processed in bounded batches and reduced in a deterministic host order.
class CudaTransportBackend final : public ITransportBackend {
public:
    SimulationResult run(
        const SimulationProblem& problem, const ProgressSink& progress = {},
        const std::atomic_bool* cancel = nullptr) const override;
    [[nodiscard]] std::string name() const override { return "cuda"; }
};

} // namespace fruitsim

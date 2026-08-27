#pragma once

#include "fruitsim/transport/simulation.hpp"

namespace fruitsim {

class CpuTransportBackend final : public ITransportBackend {
public:
    SimulationResult run(
        const SimulationProblem& problem, const ProgressSink& progress = {},
        const std::atomic_bool* cancel = nullptr) const override;
    [[nodiscard]] std::string name() const override { return "cpu"; }
};

} // namespace fruitsim

#include "fruitsim/cuda/cuda_backend.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace fruitsim {
namespace {

constexpr float kPi = 3.14159265358979323846F;
constexpr std::size_t kMaximumTrajectoryPoints = 1000000;

void check_cuda(cudaError_t status, const char* operation)
{
    if (status != cudaSuccess) {
        std::ostringstream message;
        message << operation << ": " << cudaGetErrorString(status);
        throw std::runtime_error(message.str());
    }
}

template <class T>
class DeviceBuffer {
public:
    DeviceBuffer() = default;
    explicit DeviceBuffer(std::size_t count) : count_(count)
    {
        if (count_ > 0) check_cuda(cudaMalloc(&pointer_, count_ * sizeof(T)), "cudaMalloc");
    }
    ~DeviceBuffer() { if (pointer_) cudaFree(pointer_); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
    [[nodiscard]] T* get() const { return pointer_; }

    void zero() const
    {
        if (count_ > 0) check_cuda(cudaMemset(pointer_, 0, count_ * sizeof(T)), "cudaMemset");
    }
    void copy_from(const std::vector<T>& values) const
    {
        if (values.size() != count_) throw std::logic_error("CUDA buffer size mismatch");
        if (count_ > 0) check_cuda(cudaMemcpy(pointer_, values.data(), count_ * sizeof(T),
            cudaMemcpyHostToDevice), "cudaMemcpy host to device");
    }
    [[nodiscard]] std::vector<T> copy_to_host() const
    {
        std::vector<T> values(count_);
        if (count_ > 0) check_cuda(cudaMemcpy(values.data(), pointer_, count_ * sizeof(T),
            cudaMemcpyDeviceToHost), "cudaMemcpy device to host");
        return values;
    }

private:
    T* pointer_ = nullptr;
    std::size_t count_ = 0;
};

struct DeviceOptical {
    float mu_a;
    float mu_s;
    float g;
    float refractive_index;
};

struct DeviceTrajectory {
    std::uint64_t photon_id;
    std::uint32_t event;
    float x;
    float y;
    float z;
    double weight;
    int region;
};

struct DeviceProblem {
    float3 center;
    const float* radii;
    int region_count;
    float exterior_refractive_index;
    float3 source_position;
    float3 source_direction;
    int gaussian_source;
    float gaussian_sigma;
    const DeviceOptical* optical;
    std::uint64_t seed;
    std::uint32_t max_events;
    float roulette_threshold;
    float roulette_survival;
    float boundary_epsilon;
    float boundary_nudge;
    int radial_bins;
    float radial_max;
    int grid_size;
    int depth_bins;
    std::uint64_t trajectory_limit;
    DeviceTrajectory* trajectories;
    unsigned long long* trajectory_count;
    unsigned long long trajectory_capacity;
    double* absorption_grid;
};

struct DeviceBatchOutput {
    double* entry_reflected;
    double* exit_reflected;
    double* transmitted;
    double* discarded;
    double* absorbed;
    int* reflected_bin;
    unsigned int* depth_bin;
    unsigned char* termination_code;
};

struct DeviceRng {
    std::uint64_t seed;
    std::uint64_t photon_id;
    std::uint64_t block = 0;
    std::uint32_t values[4]{};
    std::uint32_t index = 4;

    __device__ static std::uint32_t high32(std::uint64_t value)
    {
        return static_cast<std::uint32_t>(value >> 32U);
    }
    __device__ void refill()
    {
        constexpr std::uint32_t m0 = 0xD2511F53U;
        constexpr std::uint32_t m1 = 0xCD9E8D57U;
        constexpr std::uint32_t w0 = 0x9E3779B9U;
        constexpr std::uint32_t w1 = 0xBB67AE85U;
        std::uint32_t c0 = static_cast<std::uint32_t>(block);
        std::uint32_t c1 = high32(block);
        std::uint32_t c2 = static_cast<std::uint32_t>(photon_id);
        std::uint32_t c3 = high32(photon_id);
        std::uint32_t k0 = static_cast<std::uint32_t>(seed);
        std::uint32_t k1 = high32(seed);
        for (int round = 0; round < 10; ++round) {
            const std::uint64_t p0 = static_cast<std::uint64_t>(m0) * c0;
            const std::uint64_t p1 = static_cast<std::uint64_t>(m1) * c2;
            const std::uint32_t n0 = high32(p1) ^ c1 ^ k0;
            const std::uint32_t n1 = static_cast<std::uint32_t>(p1);
            const std::uint32_t n2 = high32(p0) ^ c3 ^ k1;
            const std::uint32_t n3 = static_cast<std::uint32_t>(p0);
            c0 = n0; c1 = n1; c2 = n2; c3 = n3;
            k0 += w0; k1 += w1;
        }
        values[0] = c0; values[1] = c1; values[2] = c2; values[3] = c3;
        index = 0;
        ++block;
    }
    __device__ double uniform_open()
    {
        if (index == 4) refill();
        return (static_cast<double>(values[index++]) + 0.5) / 4294967296.0;
    }
};

__device__ float3 add(float3 a, float3 b)
{
    return make_float3(a.x + b.x, a.y + b.y, a.z + b.z);
}
__device__ float3 sub(float3 a, float3 b)
{
    return make_float3(a.x - b.x, a.y - b.y, a.z - b.z);
}
__device__ float3 mul(float scale, float3 value)
{
    return make_float3(scale * value.x, scale * value.y, scale * value.z);
}
__device__ float dot3(float3 a, float3 b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}
__device__ float3 cross3(float3 a, float3 b)
{
    return make_float3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x);
}
__device__ float3 normalized(float3 value)
{
    return mul(rsqrtf(fmaxf(dot3(value, value), 1.0e-30F)), value);
}

__device__ bool sphere_roots(
    float3 origin, float3 direction, float3 center, float radius, float& near_t, float& far_t)
{
    const float3 offset = sub(origin, center);
    const float a = dot3(direction, direction);
    const float half_b = dot3(offset, direction);
    const float c = dot3(offset, offset) - radius * radius;
    const float discriminant = half_b * half_b - a * c;
    if (discriminant < 0.0F) return false;
    const float root = sqrtf(discriminant);
    near_t = (-half_b - root) / a;
    far_t = (-half_b + root) / a;
    return true;
}

__device__ bool first_entry(const DeviceProblem& problem, float3 origin, float3 direction,
    float3& position, float3& inward)
{
    float near_t = 0.0F;
    float far_t = 0.0F;
    if (!sphere_roots(origin, direction, problem.center,
            problem.radii[problem.region_count - 1], near_t, far_t)) return false;
    float distance = INFINITY;
    if (near_t > problem.boundary_epsilon) distance = near_t;
    if (far_t > problem.boundary_epsilon) distance = fminf(distance, far_t);
    if (!isfinite(distance)) return false;
    position = add(origin, mul(distance, direction));
    inward = mul(-1.0F, normalized(sub(position, problem.center)));
    return true;
}

__device__ bool next_boundary(const DeviceProblem& problem, float3 origin, float3 direction,
    int current_region, float& distance, float3& position, float3& normal, int& next_region)
{
    distance = INFINITY;
    int boundary_index = -1;
    next_region = -1;

    // In a concentric layered sphere, a photon can only meet the current
    // region's outer sphere or (except in the core) its adjacent inner sphere.
    // Determining the target from topology avoids a fragile post-hit region
    // sample for nearly tangent float-valued paths.
    float near_t = 0.0F;
    float far_t = 0.0F;
    if (sphere_roots(origin, direction, problem.center,
            problem.radii[current_region], near_t, far_t)) {
        const float candidates[2] = {near_t, far_t};
        for (int index = 0; index < 2; ++index) {
            const float candidate = candidates[index];
            if (candidate > problem.boundary_epsilon && candidate < distance) {
                distance = candidate;
                boundary_index = current_region;
                next_region = current_region + 1 < problem.region_count
                    ? current_region + 1 : -1;
            }
        }
    }
    if (current_region > 0 && sphere_roots(origin, direction, problem.center,
            problem.radii[current_region - 1], near_t, far_t)) {
        const float candidates[2] = {near_t, far_t};
        for (int index = 0; index < 2; ++index) {
            const float candidate = candidates[index];
            if (candidate > problem.boundary_epsilon && candidate < distance) {
                distance = candidate;
                boundary_index = current_region - 1;
                next_region = current_region - 1;
            }
        }
    }
    if (boundary_index < 0 || !isfinite(distance)) {
        const float3 local = sub(origin, problem.center);
        const float radius = sqrtf(fmaxf(0.0F, dot3(local, local)));
        const float radial_direction = dot3(local, direction);
        const float tolerance = problem.boundary_nudge * 8.0F;
        const float outer_radius = problem.radii[current_region];
        if (radial_direction >= 0.0F && radius >= outer_radius - tolerance) {
            distance = 0.0F;
            boundary_index = current_region;
            next_region = current_region + 1 < problem.region_count
                ? current_region + 1 : -1;
        } else if (current_region > 0 && radial_direction < 0.0F
            && radius <= problem.radii[current_region - 1] + tolerance) {
            distance = 0.0F;
            boundary_index = current_region - 1;
            next_region = current_region - 1;
        } else {
            return false;
        }
    }
    position = add(origin, mul(distance, direction));
    const float3 outward = mul(1.0F / problem.radii[boundary_index],
        sub(position, problem.center));
    normal = next_region >= 0 && next_region < current_region
        ? mul(-1.0F, outward) : outward;
    return true;
}

struct DeviceFresnel {
    float reflectance;
    bool total_internal_reflection;
};

__device__ DeviceFresnel fresnel(float cos_incident, float n1, float n2)
{
    const float ci = fminf(1.0F, fmaxf(0.0F, cos_incident));
    const float eta = n1 / n2;
    const float sin_t_squared = eta * eta * fmaxf(0.0F, 1.0F - ci * ci);
    if (sin_t_squared >= 1.0F) return {1.0F, true};
    const float ct = sqrtf(fmaxf(0.0F, 1.0F - sin_t_squared));
    const float rs_den = n1 * ci + n2 * ct;
    const float rp_den = n1 * ct + n2 * ci;
    const float rs = rs_den == 0.0F ? 1.0F : (n1 * ci - n2 * ct) / rs_den;
    const float rp = rp_den == 0.0F ? 1.0F : (n1 * ct - n2 * ci) / rp_den;
    return {0.5F * (rs * rs + rp * rp), false};
}

__device__ float3 reflected(float3 incident, float3 normal)
{
    return normalized(sub(incident, mul(2.0F * dot3(incident, normal), normal)));
}

__device__ float3 refracted(float3 incident, float3 normal, float n1, float n2)
{
    const float cos_i = fminf(1.0F, fmaxf(0.0F, dot3(incident, normal)));
    const float eta = n1 / n2;
    const float3 tangent = sub(incident, mul(cos_i, normal));
    const float transmitted_tangent_squared = eta * eta * dot3(tangent, tangent);
    const float cos_t = sqrtf(fmaxf(0.0F, 1.0F - transmitted_tangent_squared));
    return normalized(add(mul(eta, tangent), mul(cos_t, normal)));
}

__device__ float3 scattered(float3 incident, float g, DeviceRng& rng)
{
    const float3 w = normalized(incident);
    const float3 helper = fabsf(w.z) < 0.999F ? make_float3(0.0F, 0.0F, 1.0F)
                                               : make_float3(1.0F, 0.0F, 0.0F);
    const float3 u = normalized(cross3(helper, w));
    const float3 v = cross3(w, u);
    const float xi = static_cast<float>(rng.uniform_open());
    float cos_theta = 2.0F * xi - 1.0F;
    if (fabsf(g) >= 1.0e-6F) {
        const float ratio = (1.0F - g * g) / (1.0F - g + 2.0F * g * xi);
        cos_theta = fminf(1.0F, fmaxf(-1.0F,
            (1.0F + g * g - ratio * ratio) / (2.0F * g)));
    }
    const float sin_theta = sqrtf(fmaxf(0.0F, 1.0F - cos_theta * cos_theta));
    const float phi = 2.0F * kPi * static_cast<float>(rng.uniform_open());
    return normalized(add(add(mul(sin_theta * cosf(phi), u),
                              mul(sin_theta * sinf(phi), v)),
        mul(cos_theta, w)));
}

__device__ void record_trajectory(const DeviceProblem& problem, std::uint64_t photon_id,
    std::uint32_t event, float3 position, double weight, int region)
{
    if (photon_id >= problem.trajectory_limit || !problem.trajectories) return;
    const unsigned long long slot = atomicAdd(problem.trajectory_count, 1ULL);
    if (slot < problem.trajectory_capacity) {
        problem.trajectories[slot] = {
            photon_id, event, position.x, position.y, position.z, weight, region};
    }
}

__device__ int radial_bin(const DeviceProblem& problem, float3 point, float3 entry)
{
    const float3 offset = sub(point, entry);
    const float3 radial = sub(offset,
        mul(dot3(offset, problem.source_direction), problem.source_direction));
    const float radius = sqrtf(fmaxf(0.0F, dot3(radial, radial)));
    const int bin = static_cast<int>(floorf(
        radius / problem.radial_max * static_cast<float>(problem.radial_bins)));
    return min(problem.radial_bins - 1, max(0, bin));
}

__device__ std::size_t grid_index(const DeviceProblem& problem, float3 point)
{
    const float radius = problem.radii[problem.region_count - 1];
    const float3 local = sub(point, problem.center);
    int x = static_cast<int>(floorf(
        (local.x + radius) / (2.0F * radius) * problem.grid_size));
    int y = static_cast<int>(floorf(
        (local.y + radius) / (2.0F * radius) * problem.grid_size));
    int z = static_cast<int>(floorf(
        (local.z + radius) / (2.0F * radius) * problem.grid_size));
    x = min(problem.grid_size - 1, max(0, x));
    y = min(problem.grid_size - 1, max(0, y));
    z = min(problem.grid_size - 1, max(0, z));
    return (static_cast<std::size_t>(z) * problem.grid_size + y) * problem.grid_size + x;
}

__global__ void transport_kernel(DeviceProblem problem, DeviceBatchOutput output,
    std::uint64_t first_photon, std::uint64_t photon_count)
{
    const std::uint64_t local = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (local >= photon_count) return;
    const std::uint64_t photon_id = first_photon + local;
    output.entry_reflected[local] = 0.0;
    output.exit_reflected[local] = 0.0;
    output.transmitted[local] = 0.0;
    output.discarded[local] = 0.0;
    output.reflected_bin[local] = -1;
    output.depth_bin[local] = 0;
    output.termination_code[local] = 0;
    for (int r = 0; r < problem.region_count; ++r) {
        output.absorbed[local * problem.region_count + r] = 0.0;
    }

    DeviceRng rng{problem.seed, photon_id};
    float3 launch = problem.source_position;
    if (problem.gaussian_source) {
        const float3 helper = fabsf(problem.source_direction.z) < 0.999F
            ? make_float3(0.0F, 0.0F, 1.0F) : make_float3(1.0F, 0.0F, 0.0F);
        const float3 source_u = normalized(cross3(helper, problem.source_direction));
        const float3 source_v = cross3(problem.source_direction, source_u);
        const float radius = problem.gaussian_sigma
            * sqrtf(-2.0F * logf(static_cast<float>(rng.uniform_open())));
        const float phi = 2.0F * kPi * static_cast<float>(rng.uniform_open());
        launch = add(launch, add(mul(radius * cosf(phi), source_u),
                                 mul(radius * sinf(phi), source_v)));
    }

    float3 position{};
    float3 entry_normal{};
    if (!first_entry(problem, launch, problem.source_direction, position, entry_normal)) {
        output.discarded[local] = 1.0;
        return;
    }
    const float3 entry_position = position;
    float3 direction = problem.source_direction;
    int region = problem.region_count - 1;
    const float n_inside = problem.optical[region].refractive_index;
    const DeviceFresnel entry_fresnel = fresnel(
        dot3(direction, entry_normal), problem.exterior_refractive_index, n_inside);
    output.entry_reflected[local] = entry_fresnel.reflectance;
    double weight = 1.0 - static_cast<double>(entry_fresnel.reflectance);
    if (weight <= 0.0) return;
    direction = refracted(direction, entry_normal,
        problem.exterior_refractive_index, n_inside);
    position = add(position, mul(problem.boundary_nudge, direction));
    std::uint32_t event = 0;
    record_trajectory(problem, photon_id, event, position, weight, region);

    float maximum_depth = 0.0F;
    bool alive = true;
    while (alive && event < problem.max_events) {
        double optical_depth = -log(rng.uniform_open());
        bool reached_collision = false;
        while (alive && !reached_collision && event < problem.max_events) {
            const DeviceOptical properties = problem.optical[region];
            const float mu_t = properties.mu_a + properties.mu_s;
            float boundary_distance = 0.0F;
            float3 boundary_position{};
            float3 boundary_normal{};
            int next_region = -1;
            if (!next_boundary(problem, position, direction, region,
                    boundary_distance, boundary_position, boundary_normal, next_region)) {
                output.discarded[local] += weight;
                output.termination_code[local] = 1;
                alive = false;
                break;
            }
            const double collision_distance = mu_t > 0.0F
                ? optical_depth / static_cast<double>(mu_t) : INFINITY;
            if (collision_distance < boundary_distance) {
                position = add(position, mul(static_cast<float>(collision_distance), direction));
                maximum_depth = fmaxf(maximum_depth,
                    fmaxf(0.0F, dot3(sub(position, entry_position), problem.source_direction)));
                const double absorbed = mu_t > 0.0F
                    ? weight * static_cast<double>(properties.mu_a / mu_t) : 0.0;
                output.absorbed[local * problem.region_count + region] += absorbed;
                if (problem.absorption_grid && absorbed > 0.0) {
                    atomicAdd(&problem.absorption_grid[grid_index(problem, position)], absorbed);
                }
                weight -= absorbed;
                ++event;
                record_trajectory(problem, photon_id, event, position, weight, region);
                if (properties.mu_s <= 0.0F || weight <= 0.0) {
                    alive = false;
                    reached_collision = true;
                    break;
                }
                direction = scattered(direction, properties.g, rng);
                reached_collision = true;
            } else {
                position = boundary_position;
                if (mu_t > 0.0F) {
                    optical_depth = fmax(0.0,
                        optical_depth - static_cast<double>(mu_t * boundary_distance));
                }
                const float n1 = properties.refractive_index;
                const float n2 = next_region < 0 ? problem.exterior_refractive_index
                                                  : problem.optical[next_region].refractive_index;
                const DeviceFresnel boundary_fresnel = fresnel(
                    dot3(direction, boundary_normal), n1, n2);
                ++event;
                if (boundary_fresnel.total_internal_reflection
                    || rng.uniform_open() < boundary_fresnel.reflectance) {
                    direction = reflected(direction, boundary_normal);
                    position = add(position, mul(problem.boundary_nudge, direction));
                    record_trajectory(problem, photon_id, event, position, weight, region);
                    continue;
                }
                direction = refracted(direction, boundary_normal, n1, n2);
                region = next_region;
                position = add(position, mul(problem.boundary_nudge, direction));
                record_trajectory(problem, photon_id, event, position, weight, region);
                if (region < 0) {
                    if (dot3(boundary_normal, problem.source_direction) < 0.0F) {
                        output.exit_reflected[local] = weight;
                        output.reflected_bin[local] = radial_bin(
                            problem, boundary_position, entry_position);
                    } else {
                        output.transmitted[local] = weight;
                    }
                    alive = false;
                }
            }
        }
        if (alive && weight < problem.roulette_threshold) {
            if (rng.uniform_open() <= problem.roulette_survival) {
                weight /= problem.roulette_survival;
            } else {
                output.discarded[local] += weight;
                output.termination_code[local] = 2;
                alive = false;
            }
        }
    }
    if (alive) {
        output.discarded[local] += weight;
        output.termination_code[local] = 3;
    }
    const float max_depth = 2.0F * problem.radii[problem.region_count - 1];
    const int bin = static_cast<int>(maximum_depth / max_depth * problem.depth_bins);
    output.depth_bin[local] = static_cast<unsigned int>(
        min(problem.depth_bins - 1, max(0, bin)));
}

double standard_error(const std::vector<double>& values)
{
    if (values.size() < 2) return 0.0;
    const double mean = std::accumulate(values.begin(), values.end(), 0.0) / values.size();
    double squared = 0.0;
    for (double value : values) squared += (value - mean) * (value - mean);
    return std::sqrt(squared / (values.size() - 1) / values.size());
}

double histogram_quantile(
    const std::vector<std::uint64_t>& histogram, double quantile, double max_depth)
{
    const std::uint64_t total = std::accumulate(
        histogram.begin(), histogram.end(), std::uint64_t{0});
    if (total == 0) return 0.0;
    const std::uint64_t target = static_cast<std::uint64_t>(std::ceil(quantile * total));
    std::uint64_t cumulative = 0;
    for (std::size_t index = 0; index < histogram.size(); ++index) {
        cumulative += histogram[index];
        if (cumulative >= target) {
            return (static_cast<double>(index) + 0.5) / histogram.size() * max_depth;
        }
    }
    return max_depth;
}

float3 to_float3(const Vec3& value)
{
    return make_float3(static_cast<float>(value.x()), static_cast<float>(value.y()),
        static_cast<float>(value.z()));
}

} // namespace

std::vector<CudaDeviceInfo> enumerate_cuda_devices()
{
    int count = 0;
    if (cudaGetDeviceCount(&count) != cudaSuccess) return {};
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

SimulationResult CudaTransportBackend::run(const SimulationProblem& problem,
    const ProgressSink& progress, const std::atomic_bool* cancel) const
{
    problem.validate();
    int device_count = 0;
    check_cuda(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount");
    if (device_count == 0) throw std::runtime_error("No CUDA device is available");
    int active_device = 0;
    int driver_version = 0;
    int runtime_version = 0;
    cudaDeviceProp device_properties{};
    check_cuda(cudaGetDevice(&active_device), "cudaGetDevice");
    check_cuda(cudaGetDeviceProperties(&device_properties, active_device),
        "cudaGetDeviceProperties");
    check_cuda(cudaDriverGetVersion(&driver_version), "cudaDriverGetVersion");
    check_cuda(cudaRuntimeGetVersion(&runtime_version), "cudaRuntimeGetVersion");

    const auto started = std::chrono::steady_clock::now();
    SimulationResult output;
    output.backend = name();
    output.runtime_metadata = {
        {"device_index", std::to_string(active_device)},
        {"device_name", device_properties.name},
        {"compute_capability", std::to_string(device_properties.major) + "."
            + std::to_string(device_properties.minor)},
        {"cuda_driver_version", std::to_string(driver_version)},
        {"cuda_runtime_version", std::to_string(runtime_version)},
        {"cuda_toolkit_version", std::to_string(CUDART_VERSION)},
        {"state_precision", "float"},
        {"tally_precision", "double"},
        {"threads_per_block", "256"},
        {"reduction", "per_photon_fixed_host_order"},
    };
    const std::size_t region_count = problem.domain.layers().size();
    std::vector<float> radii;
    for (const auto& layer : problem.domain.layers()) {
        radii.push_back(static_cast<float>(layer.outer_radius_mm));
    }
    DeviceBuffer<float> device_radii(radii.size());
    device_radii.copy_from(radii);

    const std::uint64_t total = problem.execution.photons_per_wavelength;
    const std::uint64_t requested_batch_size = problem.execution.batch_size;
    const std::size_t requested_batches = static_cast<std::size_t>(
        (total + requested_batch_size - 1) / requested_batch_size);
    const std::size_t batch_count = std::min(
        requested_batches, problem.execution.max_reduction_batches);
    const std::uint64_t largest_batch = (total + batch_count - 1) / batch_count;
    const double cuda_boundary_nudge = std::max(
        problem.execution.boundary_epsilon_mm,
        16.0 * std::numeric_limits<float>::epsilon()
            * problem.domain.outer_radius_mm());
    output.runtime_metadata["boundary_nudge_mm"] = std::to_string(cuda_boundary_nudge);
    DeviceBuffer<double> device_entry_reflected(largest_batch);
    DeviceBuffer<double> device_exit_reflected(largest_batch);
    DeviceBuffer<double> device_transmitted(largest_batch);
    DeviceBuffer<double> device_discarded(largest_batch);
    DeviceBuffer<double> device_absorbed(largest_batch * region_count);
    DeviceBuffer<int> device_reflected_bin(largest_batch);
    DeviceBuffer<unsigned int> device_depth_bin(largest_batch);
    DeviceBuffer<unsigned char> device_termination_code(largest_batch);

    for (std::size_t wavelength_index = 0;
         wavelength_index < problem.spectra.size(); ++wavelength_index) {
        if (cancel && cancel->load()) break;
        const auto& spectrum = problem.spectra[wavelength_index];
        std::vector<DeviceOptical> optical;
        for (const auto& properties : spectrum.regions) {
            optical.push_back({static_cast<float>(properties.mu_a_mm_inv),
                static_cast<float>(properties.mu_s_mm_inv), static_cast<float>(properties.g),
                static_cast<float>(properties.refractive_index)});
        }
        DeviceBuffer<DeviceOptical> device_optical(optical.size());
        device_optical.copy_from(optical);

        const std::size_t grid_cells = problem.scoring.grid_size == 0 ? 0
            : problem.scoring.grid_size * problem.scoring.grid_size * problem.scoring.grid_size;
        DeviceBuffer<double> device_grid(grid_cells);
        device_grid.zero();

        std::size_t trajectory_capacity = 0;
        if (problem.scoring.trajectory_limit > 0) {
            const std::size_t points_per_photon = std::min<std::size_t>(
                static_cast<std::size_t>(problem.execution.max_events) + 2, 4096);
            trajectory_capacity = problem.scoring.trajectory_limit
                    > kMaximumTrajectoryPoints / points_per_photon
                ? kMaximumTrajectoryPoints
                : std::min(kMaximumTrajectoryPoints,
                    problem.scoring.trajectory_limit * points_per_photon);
        }
        DeviceBuffer<DeviceTrajectory> device_trajectories(trajectory_capacity);
        DeviceBuffer<unsigned long long> device_trajectory_count(trajectory_capacity > 0 ? 1 : 0);
        device_trajectory_count.zero();

        DeviceProblem device_problem{};
        device_problem.center = to_float3(problem.domain.center());
        device_problem.radii = device_radii.get();
        device_problem.region_count = static_cast<int>(region_count);
        device_problem.exterior_refractive_index = static_cast<float>(
            problem.exterior_refractive_index);
        device_problem.source_position = to_float3(problem.source.position_mm);
        device_problem.source_direction = to_float3(problem.source.direction.normalize());
        device_problem.gaussian_source = problem.source.type == "gaussian";
        device_problem.gaussian_sigma = static_cast<float>(problem.source.gaussian_sigma_mm);
        device_problem.optical = device_optical.get();
        device_problem.seed = problem.execution.seed + wavelength_index;
        device_problem.max_events = problem.execution.max_events;
        device_problem.roulette_threshold = static_cast<float>(
            problem.execution.roulette_threshold);
        device_problem.roulette_survival = static_cast<float>(
            problem.execution.roulette_survival);
        device_problem.boundary_epsilon = static_cast<float>(
            problem.execution.boundary_epsilon_mm);
        // A configured epsilon can be representable in double but disappear when a
        // float position is near the 40 mm apple surface. Only the position nudge is
        // ULP-scaled; the intersection threshold retains the configured value so
        // near-tangent physical paths are not discarded.
        device_problem.boundary_nudge = static_cast<float>(cuda_boundary_nudge);
        device_problem.radial_bins = static_cast<int>(problem.scoring.radial_bins);
        device_problem.radial_max = static_cast<float>(problem.scoring.radial_max_mm);
        device_problem.grid_size = static_cast<int>(problem.scoring.grid_size);
        device_problem.depth_bins = static_cast<int>(problem.scoring.depth_bins);
        device_problem.trajectory_limit = problem.scoring.trajectory_limit;
        device_problem.trajectories = device_trajectories.get();
        device_problem.trajectory_count = device_trajectory_count.get();
        device_problem.trajectory_capacity = trajectory_capacity;
        device_problem.absorption_grid = device_grid.get();

        WavelengthResult result;
        result.wavelength_nm = spectrum.wavelength_nm;
        result.absorbed_by_region.assign(region_count, 0.0);
        result.radial_reflectance.assign(problem.scoring.radial_bins, 0.0);
        std::vector<std::uint64_t> depth_histogram(problem.scoring.depth_bins, 0);
        std::vector<double> batch_reflectance;
        std::vector<double> batch_transmittance;

        for (std::size_t batch_index = 0; batch_index < batch_count; ++batch_index) {
            if (cancel && cancel->load()) break;
            const std::uint64_t first = total * batch_index / batch_count;
            const std::uint64_t end = total * (batch_index + 1) / batch_count;
            const std::uint64_t count = end - first;
            DeviceBatchOutput device_output{device_entry_reflected.get(),
                device_exit_reflected.get(), device_transmitted.get(), device_discarded.get(),
                device_absorbed.get(), device_reflected_bin.get(), device_depth_bin.get(),
                device_termination_code.get()};
            constexpr unsigned int threads = 256;
            const unsigned int blocks = static_cast<unsigned int>((count + threads - 1) / threads);
            transport_kernel<<<blocks, threads>>>(device_problem, device_output, first, count);
            check_cuda(cudaGetLastError(), "launch transport_kernel");
            check_cuda(cudaDeviceSynchronize(), "execute transport_kernel");

            const auto entry_reflected_all = device_entry_reflected.copy_to_host();
            const auto exit_reflected_all = device_exit_reflected.copy_to_host();
            const auto transmitted_all = device_transmitted.copy_to_host();
            const auto discarded_all = device_discarded.copy_to_host();
            const auto absorbed_all = device_absorbed.copy_to_host();
            const auto reflected_bins_all = device_reflected_bin.copy_to_host();
            const auto depth_bins_all = device_depth_bin.copy_to_host();
            const auto termination_codes_all = device_termination_code.copy_to_host();
            double batch_r = 0.0;
            double batch_t = 0.0;
            for (std::uint64_t local = 0; local < count; ++local) {
                const double entry_reflected = entry_reflected_all[local];
                const double exit_reflected = exit_reflected_all[local];
                batch_r += entry_reflected + exit_reflected;
                batch_t += transmitted_all[local];
                result.discarded_weight += discarded_all[local];
                result.radial_reflectance[0] += entry_reflected;
                if (reflected_bins_all[local] >= 0) {
                    result.radial_reflectance[static_cast<std::size_t>(
                        reflected_bins_all[local])] += exit_reflected;
                }
                ++depth_histogram[depth_bins_all[local]];
                if (termination_codes_all[local] == 1) ++result.boundary_failures;
                if (termination_codes_all[local] == 3) ++result.max_event_terminations;
                for (std::size_t region = 0; region < region_count; ++region) {
                    result.absorbed_by_region[region] +=
                        absorbed_all[local * region_count + region];
                }
            }
            result.reflectance += batch_r;
            result.transmittance += batch_t;
            result.photons += count;
            batch_reflectance.push_back(batch_r / count);
            batch_transmittance.push_back(batch_t / count);
            if (progress) progress({wavelength_index, result.photons, total});
        }

        if (result.photons > 0) {
            const double scale = 1.0 / result.photons;
            result.reflectance *= scale;
            result.transmittance *= scale;
            result.discarded_weight *= scale;
            for (double& value : result.absorbed_by_region) value *= scale;
            for (double& value : result.radial_reflectance) value *= scale;
            result.absorption_grid = device_grid.copy_to_host();
            for (double& value : result.absorption_grid) value *= scale;
        }
        result.reflectance_standard_error = standard_error(batch_reflectance);
        result.transmittance_standard_error = standard_error(batch_transmittance);
        const double absorbed = std::accumulate(
            result.absorbed_by_region.begin(), result.absorbed_by_region.end(), 0.0);
        result.energy_residual = 1.0 - result.reflectance - result.transmittance
            - absorbed - result.discarded_weight;
        const double max_depth = 2.0 * problem.domain.outer_radius_mm();
        result.penetration_q50_mm = histogram_quantile(depth_histogram, 0.5, max_depth);
        result.penetration_q90_mm = histogram_quantile(depth_histogram, 0.9, max_depth);

        if (trajectory_capacity > 0) {
            const auto count_value = device_trajectory_count.copy_to_host();
            const std::size_t points = std::min<std::size_t>(trajectory_capacity,
                static_cast<std::size_t>(count_value.front()));
            const auto raw = device_trajectories.copy_to_host();
            result.trajectories.reserve(points);
            for (std::size_t index = 0; index < points; ++index) {
                const auto& point = raw[index];
                result.trajectories.push_back({point.photon_id, point.event,
                    {point.x, point.y, point.z}, point.weight, point.region});
            }
            std::sort(result.trajectories.begin(), result.trajectories.end(),
                [](const auto& left, const auto& right) {
                    return left.photon_id < right.photon_id
                        || (left.photon_id == right.photon_id && left.event < right.event);
                });
        }
        output.wavelengths.push_back(std::move(result));
    }
    output.elapsed_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    return output;
}

} // namespace fruitsim

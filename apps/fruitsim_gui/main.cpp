#include "fruitsim/io/config_loader.hpp"
#include "fruitsim/io/result_writer.hpp"
#include "fruitsim/runtime/cpu_backend.hpp"

#include "imgui.h"
#include "imgui_impl_glfw.h"
#include "imgui_impl_opengl3.h"
#include "implot.h"
#include <GLFW/glfw3.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <future>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct SpectralSummary {
    std::vector<double> wavelength;
    std::vector<double> reflectance;
    std::vector<double> transmittance;
    std::vector<double> absorption;
};

struct ModelMetric {
    std::string run_id;
    double rmsep = 0.0;
    double r2 = 0.0;
    double rp = 0.0;
    double rpd = 0.0;
};

std::future<std::string> run_simulation(std::string config, std::string output)
{
    return std::async(std::launch::async, [config = std::move(config), output = std::move(output)] {
        try {
            auto problem = fruitsim::load_simulation_config(config);
            fruitsim::CpuTransportBackend backend;
            auto result = backend.run(problem);
            fruitsim::write_simulation_results(problem, result, output);
            return std::string{"Simulation completed"};
        } catch (const std::exception& error) {
            return std::string{"Simulation failed: "} + error.what();
        }
    });
}

std::future<std::string> run_ml_job(std::string python, std::string config)
{
    return std::async(std::launch::async, [python = std::move(python), config = std::move(config)] {
        if (python.find('\'') != std::string::npos || config.find('\'') != std::string::npos) {
            return std::string{"ML job rejected: paths cannot contain a single quote"};
        }
        const std::string command = "PYTHONPATH=python '" + python
            + "' -m fruitsim_ml train --config '" + config + "'";
        const int status = std::system(command.c_str());
        return status == 0 ? std::string{"ML comparison completed"}
                           : std::string{"ML comparison failed; inspect terminal output"};
    });
}

SpectralSummary load_summary(const std::filesystem::path& path)
{
    SpectralSummary result;
    std::ifstream stream(path);
    std::string line;
    std::getline(stream, line);
    while (std::getline(stream, line)) {
        std::stringstream fields(line);
        std::string value;
        std::vector<double> row;
        while (std::getline(fields, value, ',')) row.push_back(std::stod(value));
        if (row.size() >= 7) {
            result.wavelength.push_back(row[0]);
            result.reflectance.push_back(row[2]);
            result.transmittance.push_back(row[4]);
            result.absorption.push_back(row[6]);
        }
    }
    return result;
}

std::vector<ModelMetric> load_model_metrics(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("Cannot open " + path.string());
    nlohmann::json document;
    stream >> document;
    std::vector<ModelMetric> result;
    for (const auto& run : document.at("runs")) {
        result.push_back({
            run.at("run_id").get<std::string>(),
            run.at("rmsep").get<double>(),
            run.at("validation_r2").get<double>(),
            run.at("validation_rp").get<double>(),
            run.at("validation_rpd").get<double>(),
        });
    }
    std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
        return left.rmsep < right.rmsep;
    });
    return result;
}

} // namespace

int main()
{
    if (!glfwInit()) return 1;
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    GLFWwindow* window = glfwCreateWindow(1500, 900, "fruitsim research workbench", nullptr, nullptr);
    if (!window) return 1;
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1);

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImPlot::CreateContext();
    ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_DockingEnable;
    ImGui_ImplGlfw_InitForOpenGL(window, true);
    ImGui_ImplOpenGL3_Init("#version 330");

    std::array<char, 512> config_path{};
    std::array<char, 512> output_path{};
    std::array<char, 512> ml_config{};
    std::array<char, 512> ml_output{};
    std::array<char, 512> python_executable{};
    std::strcpy(config_path.data(), "configs/golden_delicious_demo.json");
    std::strcpy(output_path.data(), "results/golden_delicious_demo");
    std::strcpy(ml_config.data(), "configs/ml_golden_demo.json");
    std::strcpy(ml_output.data(), "results/ml_golden_demo");
    std::strcpy(python_executable.data(), "python");
    std::future<std::string> simulation;
    std::future<std::string> ml_job;
    std::string status = "Ready";
    SpectralSummary summary;
    std::vector<ModelMetric> model_metrics;

    while (!glfwWindowShouldClose(window)) {
        glfwPollEvents();
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();
        ImGui::DockSpaceOverViewport(0, ImGui::GetMainViewport());

        ImGui::Begin("Apple model");
        ImGui::Text("Cultivar: Golden Delicious");
        ImGui::Text("Geometry: core 8 mm | flesh 39 mm | skin 40 mm");
        ImGui::Text("Spectrum: 500-1000 nm");
        ImGui::TextColored({1.0F, 0.65F, 0.1F, 1.0F},
            "SYNTHETIC ASSUMPTIONS - NOT CALIBRATED FOR REAL SSC");
        ImGui::InputText("Simulation config", config_path.data(), config_path.size());
        ImGui::InputText("Output directory", output_path.data(), output_path.size());
        ImGui::End();

        ImGui::Begin("Simulation settings");
        if (ImGui::Button("Run CPU simulation")
            && (!simulation.valid()
                || simulation.wait_for(std::chrono::seconds(0)) == std::future_status::ready)) {
            simulation = run_simulation(config_path.data(), output_path.data());
            status = "Running...";
        }
        ImGui::SameLine();
        if (ImGui::Button("Load results")) {
            try {
                summary = load_summary(std::filesystem::path(output_path.data()) / "summary.csv");
                status = "Results loaded";
            } catch (const std::exception& error) {
                status = std::string{"Load failed: "} + error.what();
            }
        }
        if (simulation.valid()
            && simulation.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            status = simulation.get();
        }
        ImGui::TextWrapped("%s", status.c_str());
        ImGui::Text("CPU backend: available");
        ImGui::Text("CUDA backend: available through a CUDA-enabled CLI build");
        ImGui::End();

        ImGui::Begin("Propagation results");
        if (!summary.wavelength.empty() && ImPlot::BeginPlot("R/T/A spectra")) {
            ImPlot::SetupAxes("Wavelength (nm)", "Fraction");
            ImPlot::PlotLine("Reflectance", summary.wavelength.data(), summary.reflectance.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::PlotLine("Transmittance", summary.wavelength.data(), summary.transmittance.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::PlotLine("Absorption", summary.wavelength.data(), summary.absorption.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::EndPlot();
        } else {
            ImGui::Text("Run or load a simulation to display spectra.");
        }
        ImGui::End();

        ImGui::Begin("SSC modeling");
        ImGui::InputText("Python executable", python_executable.data(), python_executable.size());
        ImGui::InputText("ML job", ml_config.data(), ml_config.size());
        ImGui::Text("Methods: MLR | PLSR | RBF-SVR | Random Forest");
        ImGui::Text("Preprocessing: raw | scaling | SNV | Savitzky-Golay");
        if (ImGui::Button("Run model comparison")
            && (!ml_job.valid()
                || ml_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready)) {
            ml_job = run_ml_job(python_executable.data(), ml_config.data());
            status = "ML comparison running...";
        }
        if (ml_job.valid()
            && ml_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            status = ml_job.get();
        }
        ImGui::End();

        ImGui::Begin("Model comparison");
        ImGui::InputText("ML output", ml_output.data(), ml_output.size());
        if (ImGui::Button("Load model metrics")) {
            try {
                model_metrics = load_model_metrics(
                    std::filesystem::path(ml_output.data()) / "metrics.json");
                status = "Model metrics loaded";
            } catch (const std::exception& error) {
                status = std::string{"Model metrics failed: "} + error.what();
            }
        }
        ImGui::Text("Required metrics: R2, rp, RMSEC, RMSECV, RMSEP, MAE, bias, RPD");
        if (!model_metrics.empty() && ImGui::BeginTable("models", 5,
                ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_ScrollY)) {
            for (const char* heading : {"Run", "RMSEP", "R2", "rp", "RPD"}) {
                ImGui::TableSetupColumn(heading);
            }
            ImGui::TableHeadersRow();
            for (const auto& metric : model_metrics) {
                ImGui::TableNextRow();
                ImGui::TableNextColumn(); ImGui::TextUnformatted(metric.run_id.c_str());
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.rmsep);
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.r2);
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.rp);
                ImGui::TableNextColumn(); ImGui::Text("%.3f", metric.rpd);
            }
            ImGui::EndTable();
        }
        ImGui::TextColored({1.0F, 0.3F, 0.2F, 1.0F},
            "Synthetic models are method demonstrations only.");
        ImGui::End();

        ImGui::Render();
        int width = 0;
        int height = 0;
        glfwGetFramebufferSize(window, &width, &height);
        glViewport(0, 0, width, height);
        glClearColor(0.08F, 0.09F, 0.11F, 1.0F);
        glClear(GL_COLOR_BUFFER_BIT);
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        glfwSwapBuffers(window);
    }

    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImPlot::DestroyContext();
    ImGui::DestroyContext();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}

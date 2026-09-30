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

struct WorkflowStageSummary {
    std::string id;
    std::string stage;
    std::vector<std::string> methods;
    std::string input_ref;
    std::string output_kind;
    int intermediate_state_count = 0;
};

std::future<std::string> run_simulation(std::string config, std::string output)
{
    return std::async(std::launch::async, [config = std::move(config), output = std::move(output)] {
        try {
            auto problem = fruitsim::load_simulation_config(config);
            fruitsim::CpuTransportBackend backend;
            auto result = backend.run(problem);
            fruitsim::write_simulation_results(problem, result, output);
            return std::string{"仿真已完成"};
        } catch (const std::exception& error) {
            return std::string{"仿真失败，请检查配置和输入数据。"};
        }
    });
}

std::future<std::string> run_ml_job(std::string python, std::string config)
{
    return std::async(std::launch::async, [python = std::move(python), config = std::move(config)] {
        if (python.find('\'') != std::string::npos || config.find('\'') != std::string::npos) {
            return std::string{"路径格式不受支持，请检查配置路径。"};
        }
        const std::string command = "PYTHONPATH=python '" + python
            + "' -m fruitsim_ml train --config '" + config + "'";
        const int status = std::system(command.c_str());
        return status == 0 ? std::string{"模型比较已完成"}
                           : std::string{"模型比较失败，请检查配置和运行记录。"};
    });
}

std::future<std::string> run_workflow_job(std::string python, std::string run_dir, std::string output_dir)
{
    return std::async(std::launch::async, [python = std::move(python), run_dir = std::move(run_dir), output_dir = std::move(output_dir)] {
        if (python.find('\'') != std::string::npos
            || run_dir.find('\'') != std::string::npos
            || output_dir.find('\'') != std::string::npos) {
            return std::string{"路径格式不受支持，请检查输入路径。"};
        }
        const std::string command = "PYTHONPATH=python '" + python
            + "' -m fruitsim_ml run-workflow --run-dir '" + run_dir
            + "' --output '" + output_dir + "'";
        const int status = std::system(command.c_str());
        return status == 0 ? std::string{"分析流程已完成"}
                           : std::string{"分析流程失败，请检查配置和运行记录。"};
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
    if (!stream) throw std::runtime_error("无法读取文件：" + path.string());
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

std::vector<WorkflowStageSummary> load_workflow_stages(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("无法读取文件：" + path.string());
    nlohmann::json document;
    stream >> document;
    std::vector<WorkflowStageSummary> result;
    for (const auto& stage : document.at("stage_runs")) {
        WorkflowStageSummary summary;
        summary.id = stage.at("stage_run_id").get<std::string>();
        summary.stage = stage.at("stage").get<std::string>();
        summary.methods = stage.at("method_chain").get<std::vector<std::string>>();
        summary.input_ref = stage.at("input_ref").get<std::string>();
        summary.output_kind = stage.at("output_kind").get<std::string>();
        summary.intermediate_state_count = static_cast<int>(stage.at("intermediate_states").size());
        result.push_back(std::move(summary));
    }
    return result;
}

} // namespace

int main()
{
    if (!glfwInit()) return 1;
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    GLFWwindow* window = glfwCreateWindow(1500, 900, "Fruitsim 光学与数据分析", nullptr, nullptr);
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
    std::array<char, 512> workflow_run_dir{};
    std::array<char, 512> workflow_output{};
    std::array<char, 512> python_executable{};
    std::strcpy(config_path.data(), "configs/sphere_pencil.json");
    std::strcpy(output_path.data(), "results/sphere_pencil");
    std::strcpy(ml_config.data(), "configs/ml_train.json");
    std::strcpy(ml_output.data(), "results/ml_train");
    std::strcpy(workflow_run_dir.data(), "results/frontend_acceptance_20260920/student_demo_final/math_seed20260919");
    std::strcpy(workflow_output.data(), "results/ml_workflow_demo");
    std::strcpy(python_executable.data(), "python");
    std::future<std::string> simulation;
    std::future<std::string> ml_job;
    std::future<std::string> workflow_job;
    std::string status = "就绪";
    SpectralSummary summary;
    std::vector<ModelMetric> model_metrics;
    std::vector<WorkflowStageSummary> workflow_stages;

    while (!glfwWindowShouldClose(window)) {
        glfwPollEvents();
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();
        ImGui::DockSpaceOverViewport(0, ImGui::GetMainViewport());

        ImGui::Begin("苹果光学仿真");
        ImGui::Text("品种：金冠苹果");
        ImGui::Text("几何参数：果核 8 mm · 果肉 39 mm · 果皮 40 mm");
        ImGui::Text("波长范围：500–1000 nm");
        ImGui::TextColored({1.0F, 0.65F, 0.1F, 1.0F},
            "合成仿真参数尚未用真实糖度数据校准");
        ImGui::InputText("仿真配置", config_path.data(), config_path.size());
        ImGui::InputText("输出目录", output_path.data(), output_path.size());
        ImGui::End();

        ImGui::Begin("仿真设置");
        if (ImGui::Button("运行仿真")
            && (!simulation.valid()
                || simulation.wait_for(std::chrono::seconds(0)) == std::future_status::ready)) {
            simulation = run_simulation(config_path.data(), output_path.data());
            status = "正在运行仿真…";
        }
        ImGui::SameLine();
        if (ImGui::Button("读取结果")) {
            try {
                summary = load_summary(std::filesystem::path(output_path.data()) / "summary.csv");
                status = "结果已读取";
            } catch (const std::exception& error) {
                status = "无法读取结果，请检查配置和输出目录。";
            }
        }
        if (simulation.valid()
            && simulation.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            status = simulation.get();
        }
        ImGui::TextWrapped("%s", status.c_str());
        ImGui::Text("计算方式：CPU");
        ImGui::End();

        ImGui::Begin("光传播结果");
        if (!summary.wavelength.empty() && ImPlot::BeginPlot("反射、透射与吸收光谱")) {
            ImPlot::SetupAxes("波长 (nm)", "比例");
            ImPlot::PlotLine("反射率", summary.wavelength.data(), summary.reflectance.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::PlotLine("透射率", summary.wavelength.data(), summary.transmittance.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::PlotLine("吸收率", summary.wavelength.data(), summary.absorption.data(),
                static_cast<int>(summary.wavelength.size()));
            ImPlot::EndPlot();
        } else {
            ImGui::Text("运行或读取仿真后显示光谱曲线。");
        }
        ImGui::End();

        ImGui::Begin("糖度建模");
        ImGui::InputText("Python 程序", python_executable.data(), python_executable.size());
        ImGui::InputText("建模配置", ml_config.data(), ml_config.size());
        ImGui::Text("方法：MLR · PLSR · RBF-SVR · 随机森林");
        ImGui::Text("预处理：原始光谱 · 缩放 · SNV · Savitzky–Golay 平滑");
        if (ImGui::Button("比较模型")
            && (!ml_job.valid()
                || ml_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready)) {
            ml_job = run_ml_job(python_executable.data(), ml_config.data());
            status = "正在比较模型…";
        }
        if (ml_job.valid()
            && ml_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            status = ml_job.get();
        }
        ImGui::End();

        ImGui::Begin("实验分析流程");
        ImGui::InputText("输入数据目录", workflow_run_dir.data(), workflow_run_dir.size());
        ImGui::InputText("结果保存目录", workflow_output.data(), workflow_output.size());
        if (ImGui::Button("运行分析流程")
            && (!workflow_job.valid()
                || workflow_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready)) {
            workflow_job = run_workflow_job(python_executable.data(), workflow_run_dir.data(), workflow_output.data());
            status = "正在运行分析流程…";
        }
        ImGui::SameLine();
        if (ImGui::Button("读取分析结果")) {
            try {
                workflow_stages = load_workflow_stages(
                    std::filesystem::path(workflow_output.data()) / "experiment.json");
                status = "分析结果已读取";
            } catch (const std::exception& error) {
                status = "无法读取分析结果，请检查结果目录。";
            }
        }
        if (workflow_job.valid()
            && workflow_job.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            status = workflow_job.get();
        }
        if (!workflow_stages.empty() && ImGui::BeginTabBar("MLStages")) {
            for (const auto& stage : workflow_stages) {
                const std::string stage_label = stage.stage == "data_inspection" ? "输入光谱" :
                    stage.stage == "preprocessing" ? "光谱预处理" :
                    stage.stage == "feature_analysis" ? "特征分析" :
                    stage.stage == "feature_selection" ? "波长筛选" :
                    stage.stage == "modeling" ? "回归预测" :
                    stage.stage == "results" ? "验证结果" : "分析步骤";
                if (ImGui::BeginTabItem(stage_label.c_str())) {
                    ImGui::Text("方法：");
                    ImGui::SameLine();
                    for (std::size_t index = 0; index < stage.methods.size(); ++index) {
                        if (index > 0) ImGui::SameLine();
                        ImGui::TextUnformatted(stage.methods[index].c_str());
                    }
                    ImGui::EndTabItem();
                }
            }
            ImGui::EndTabBar();
        } else {
            ImGui::TextWrapped("运行或读取分析流程后，可查看输入光谱、预处理、特征分析、波长筛选、回归预测和验证结果。");
        }
        ImGui::End();

        ImGui::Begin("模型结果对比");
        ImGui::InputText("模型结果目录", ml_output.data(), ml_output.size());
        if (ImGui::Button("读取模型指标")) {
            try {
                model_metrics = load_model_metrics(
                    std::filesystem::path(ml_output.data()) / "metrics.json");
                status = "模型指标已读取";
            } catch (const std::exception& error) {
                status = "无法读取模型指标，请检查结果目录。";
            }
        }
        ImGui::Text("指标：R² · 相关系数 · RMSEC · RMSECV · RMSEP · MAE · 偏差 · RPD");
        if (!model_metrics.empty() && ImGui::BeginTable("models", 5,
                ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_ScrollY)) {
            for (const char* heading : {"流程", "RMSEP", "R²", "相关系数", "RPD"}) {
                ImGui::TableSetupColumn(heading);
            }
            ImGui::TableHeadersRow();
            for (const auto& metric : model_metrics) {
                ImGui::TableNextRow();
                ImGui::TableNextColumn(); ImGui::Text("模型 %d", static_cast<int>(&metric - model_metrics.data()) + 1);
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.rmsep);
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.r2);
                ImGui::TableNextColumn(); ImGui::Text("%.4f", metric.rp);
                ImGui::TableNextColumn(); ImGui::Text("%.3f", metric.rpd);
            }
            ImGui::EndTable();
        }
        ImGui::TextColored({1.0F, 0.3F, 0.2F, 1.0F},
            "模型结果基于合成数据，仅用于方法演示。");
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

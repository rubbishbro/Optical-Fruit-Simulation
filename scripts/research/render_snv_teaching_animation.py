"""
Fruitsim ML Pipeline Teaching Animation — Manim Demo
======================================================
This script generates a step-by-step animation explaining the SNV
(Standard Normal Variate) preprocessing step using Manim.

Run locally (requires manim >= 0.18):
    manim -pqh render_snv_teaching_animation.py SNVTeachingScene

What it demonstrates
--------------------
1. Raw spectrum appears as a curve.
2. A sample is highlighted.
3. Its mean (μ) and standard deviation (σ) are computed visually.
4. The formula x' = (x − μ) / σ is written and animated.
5. The raw curve morphs into the standardized curve.
6. A before/after comparison is shown.

Why Manim for teaching?
-----------------------
- Beautiful, smooth mathematical notation (MathTex).
- Built-in step-by-step narration via Wait() and Transform().
- Excellent for *concept introduction* videos.

Limitations in a Web UI:
------------------------
- Output is a video/GIF, not interactive.
- Students cannot click a wavelength, switch samples, or hover for values.
- Heavy dependency chain (LaTeX, OpenGL, FFmpeg).

Recommended hybrid strategy:
----------------------------
- Use Manim (or similar) for short "concept intro" clips (30-60s).
- Use simplified, interactive Canvas/SVG for the live exploration UI.
"""

from manim import *


class SNVTeachingScene(Scene):
    """A self-contained teaching animation for SNV preprocessing."""

    def construct(self):
        # ------------------------------------------------------------------
        # Configuration
        # ------------------------------------------------------------------
        raw_color = BLUE_D
        output_color = ORANGE
        mean_color = YELLOW
        std_color = GREEN
        formula_color = WHITE
        duration_per_step = 2.5

        # Synthetic wavelength axis and a sample spectrum
        wavelengths = np.linspace(700, 1100, 80)
        baseline = 0.5 + 0.3 * np.sin((wavelengths - 700) / 400 * PI)
        noise = np.random.RandomState(42).normal(0, 0.02, size=wavelengths.shape)
        raw_spectrum = baseline + noise + 0.15  # positive offset
        standardized = (raw_spectrum - raw_spectrum.mean()) / raw_spectrum.std()

        # Axes
        axes = Axes(
            x_range=[700, 1100, 100],
            y_range=[0, 1.2, 0.3],
            x_length=10,
            y_length=4,
            axis_config={"include_tip": False, "color": GRAY_B},
            tips=False,
        ).shift(UP * 0.3)

        x_label = axes.get_x_axis_label(r"\text{波长 } \lambda \text{ (nm)}")
        y_label = axes.get_y_axis_label(r"\text{信号强度}")

        # Title
        title = Text("光谱预处理：SNV 标准化", font="Source Han Sans SC", font_size=36)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("Standard Normal Variate", font_size=20, color=GRAY_C)
        subtitle.next_to(title, DOWN, buff=0.1)

        self.play(Write(title), FadeIn(subtitle))
        self.wait(0.5)

        # ------------------------------------------------------------------
        # Step 1: Show raw spectrum
        # ------------------------------------------------------------------
        raw_plot = axes.plot_line_graph(
            x_values=wavelengths,
            y_values=raw_spectrum,
            line_color=raw_color,
            add_vertex_dots=False,
        )["line_graph"]

        step1 = Text("步骤 1：原始光谱", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)
        self.play(Create(axes), Write(x_label), Write(y_label), Create(raw_plot), Write(step1))
        self.wait(duration_per_step)

        # ------------------------------------------------------------------
        # Step 2: Highlight a single sample and show mean
        # ------------------------------------------------------------------
        mean_val = raw_spectrum.mean()
        mean_line = axes.get_horizontal_line(
            axes.c2p(700, mean_val), x_range=[700, 1100], color=mean_color, stroke_width=2
        )
        mean_label = MathTex(r"\mu = {:.3f}".format(mean_val), color=mean_color, font_size=28)
        mean_label.next_to(mean_line, RIGHT)

        step2 = Text("步骤 2：计算样本均值 μ", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)
        self.play(ReplacementTransform(step1, step2))
        self.play(Create(mean_line), Write(mean_label))
        self.wait(duration_per_step)

        # ------------------------------------------------------------------
        # Step 3: Show standard deviation band
        # ------------------------------------------------------------------
        std_val = raw_spectrum.std()
        upper = axes.get_horizontal_line(
            axes.c2p(700, mean_val + std_val), x_range=[700, 1100], color=std_color, stroke_width=1.5
        )
        lower = axes.get_horizontal_line(
            axes.c2p(700, mean_val - std_val), x_range=[700, 1100], color=std_color, stroke_width=1.5
        )
        band = Polygon(
            axes.c2p(700, mean_val + std_val),
            axes.c2p(1100, mean_val + std_val),
            axes.c2p(1100, mean_val - std_val),
            axes.c2p(700, mean_val - std_val),
            fill_color=std_color,
            fill_opacity=0.15,
            stroke_width=0,
        )
        std_label = MathTex(r"\sigma = {:.3f}".format(std_val), color=std_color, font_size=28)
        std_label.next_to(upper, RIGHT)

        step3 = Text("步骤 3：计算标准差 σ", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)
        self.play(ReplacementTransform(step2, step3))
        self.play(FadeIn(band), Create(upper), Create(lower), Write(std_label))
        self.wait(duration_per_step)

        # ------------------------------------------------------------------
        # Step 4: Write the formula
        # ------------------------------------------------------------------
        formula = MathTex(r"x' = {x - \mu \over \sigma}", color=formula_color, font_size=42)
        formula.to_edge(DOWN, buff=0.8)
        step4 = Text("步骤 4：逐点变换", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)

        self.play(
            ReplacementTransform(step3, step4),
            FadeOut(band), FadeOut(upper), FadeOut(lower),
            FadeOut(mean_line), FadeOut(mean_label), FadeOut(std_label),
        )
        self.play(Write(formula))
        self.wait(duration_per_step)

        # ------------------------------------------------------------------
        # Step 5: Morph raw → standardized
        # ------------------------------------------------------------------
        # We need new axes for standardized range
        axes2 = Axes(
            x_range=[700, 1100, 100],
            y_range=[-3, 3, 1],
            x_length=10,
            y_length=4,
            axis_config={"include_tip": False, "color": GRAY_B},
            tips=False,
        ).shift(UP * 0.3)

        output_plot = axes2.plot_line_graph(
            x_values=wavelengths,
            y_values=standardized,
            line_color=output_color,
            add_vertex_dots=False,
        )["line_graph"]

        step5 = Text("步骤 5：得到标准化光谱", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)

        self.play(
            ReplacementTransform(step4, step5),
            FadeOut(formula),
            Transform(axes, axes2),
            Transform(raw_plot, output_plot),
        )
        self.wait(duration_per_step)

        # Zero line
        zero_line = axes2.get_horizontal_line(
            axes2.c2p(700, 0), x_range=[700, 1100], color=GRAY_C, stroke_width=1, stroke_opacity=0.6
        )
        self.play(Create(zero_line))
        self.wait(1.5)

        # ------------------------------------------------------------------
        # Step 6: Side-by-side before/after miniatures
        # ------------------------------------------------------------------
        step6 = Text("对比：原始 vs 标准化", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)

        mini_axes_raw = Axes(
            x_range=[700, 1100, 100],
            y_range=[0, 1.2, 0.3],
            x_length=4,
            y_length=1.8,
            axis_config={"include_tip": False, "color": GRAY_B},
            tips=False,
        ).shift(LEFT * 3 + DOWN * 1.5)

        mini_raw = mini_axes_raw.plot_line_graph(
            x_values=wavelengths,
            y_values=raw_spectrum,
            line_color=raw_color,
            add_vertex_dots=False,
        )["line_graph"]

        mini_axes_out = Axes(
            x_range=[700, 1100, 100],
            y_range=[-3, 3, 1],
            x_length=4,
            y_length=1.8,
            axis_config={"include_tip": False, "color": GRAY_B},
            tips=False,
        ).shift(RIGHT * 3 + DOWN * 1.5)

        mini_out = mini_axes_out.plot_line_graph(
            x_values=wavelengths,
            y_values=standardized,
            line_color=output_color,
            add_vertex_dots=False,
        )["line_graph"]

        label_raw = Text("原始", font_size=20, color=raw_color).next_to(mini_axes_raw, DOWN)
        label_out = Text("标准化", font_size=20, color=output_color).next_to(mini_axes_out, DOWN)

        self.play(
            ReplacementTransform(step5, step6),
            FadeOut(raw_plot),
            FadeOut(axes),
            FadeOut(zero_line),
            FadeOut(x_label),
            FadeOut(y_label),
            FadeIn(mini_axes_raw),
            FadeIn(mini_axes_out),
            Create(mini_raw),
            Create(mini_out),
            Write(label_raw),
            Write(label_out),
        )
        self.wait(3)

        # ------------------------------------------------------------------
        # Closing
        # ------------------------------------------------------------------
        closing = Text(
            "SNV 消除了基线和尺度差异，\n让样本之间的光谱形状更容易比较。",
            font_size=26,
            color=GRAY_B,
        ).to_edge(DOWN, buff=0.5)

        self.play(ReplacementTransform(step6, closing))
        self.wait(4)
        self.play(FadeOut(Group(*self.mobjects)))


# ------------------------------------------------------------------------------
# Bonus: CARS wavelength selection animation (compact version)
# ------------------------------------------------------------------------------

class CARSTeachingScene(Scene):
    """Animated illustration of CARS iterative wavelength elimination."""

    def construct(self):
        title = Text("CARS 波长筛选", font="Source Han Sans SC", font_size=36).to_edge(UP, buff=0.4)
        subtitle = Text("Competitive Adaptive Reweighted Sampling", font_size=20, color=GRAY_C)
        subtitle.next_to(title, DOWN, buff=0.1)
        self.play(Write(title), FadeIn(subtitle))

        np.random.seed(7)
        n_waves = 40
        x_pos = np.linspace(-5, 5, n_waves)
        importance = np.abs(np.random.randn(n_waves))
        importance[10:14] += 1.5  # fake important band
        importance = importance / importance.max()

        bars = VGroup()
        for i, (x, h) in enumerate(zip(x_pos, importance)):
            bar = Rectangle(width=0.18, height=h * 3, fill_color=BLUE, fill_opacity=0.8, stroke_width=0)
            bar.move_to(np.array([x, -1.5 + h * 1.5, 0]))
            bars.add(bar)

        self.play(FadeIn(bars))
        step = Text("初始：全部波长参与竞争", font_size=24, color=GRAY_B).to_edge(DOWN, buff=0.5)
        self.play(Write(step))
        self.wait(2)

        # Iteration 1: remove weakest
        survivors = list(range(n_waves))
        for iteration in range(1, 4):
            # Remove bottom 25%
            idx_importance = [(i, importance[i]) for i in survivors]
            idx_importance.sort(key=lambda t: t[1])
            n_remove = max(1, len(survivors) // 4)
            removed = [i for i, _ in idx_importance[:n_remove]]
            survivors = [i for i in survivors if i not in removed]

            anims = []
            for i in removed:
                anims.append(bars[i].animate.set_fill(GRAY_D, opacity=0.25).scale(0.6))
            new_step = Text(
                f"第 {iteration} 轮：淘汰 {n_remove} 个弱贡献波长，保留 {len(survivors)} 个",
                font_size=24, color=GRAY_B,
            ).to_edge(DOWN, buff=0.5)
            self.play(ReplacementTransform(step, new_step), *anims)
            step = new_step
            self.wait(2)

        final = Text(
            "保留的波长将进入 PLSR 回归模型",
            font_size=26, color=GRAY_B,
        ).to_edge(DOWN, buff=0.5)
        self.play(ReplacementTransform(step, final))
        self.wait(3)
        self.play(FadeOut(Group(*self.mobjects)))

"""Statistical apple-shape construction from registered point clouds."""

from .model import ShapeInstance, StatisticalFujiShape
from .training import TrainingOptions, train_statistical_shape

__all__ = [
    "ShapeInstance",
    "StatisticalFujiShape",
    "TrainingOptions",
    "train_statistical_shape",
]

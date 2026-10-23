"""The Logistics application owns one feature runtime; consumers use it directly."""
from .feature_runtime import FeatureRegistry

registry = FeatureRegistry()

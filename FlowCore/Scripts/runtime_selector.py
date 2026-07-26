#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowCore Runtime Selector v1.0
Mission 2: Compare and Select Best AI Runtime for Hardware

Compares: LiteRT, llama.cpp, ONNX Runtime, ExecuTorch, MLC LLM, GGUF, Vulkan, OpenCL
Selects optimal runtime based on hardware capabilities.
"""

import os
import json
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


class RuntimeType(Enum):
    LLAMA_CPP = "llama.cpp"
    ONNX_RUNTIME = "onnx_runtime"
    EXECUTORCH = "executortorch"
    MLC_LLM = "mlc_llm"
    LITERT = "litert"
    TFLITE = "tensorflow_lite"


class AccelerationBackend(Enum):
    CPU = "cpu"
    VULKAN = "vulkan"
    OPENCL = "opencl"
    NNAPI = "nnapi"
    HEXAGON_DSP = "hexagon_dsp"
    CUDA = "cuda"  # Not available on Android but included for completeness


@dataclass
class RuntimeScore:
    """Score for a runtime on this hardware."""
    runtime: RuntimeType
    total_score: float = 0.0
    compatibility_score: float = 0.0
    performance_score: float = 0.0
    memory_efficiency: float = 0.0
    battery_efficiency: float = 0.0
    model_support: float = 0.0
    ease_of_use: float = 0.0
    recommended: bool = False
    reasons: List[str] = field(default_factory=list)


class RuntimeSelector:
    """Intelligent runtime selector based on hardware analysis."""
    
    # Runtime capabilities matrix
    RUNTIME_CAPABILITIES = {
        RuntimeType.LLAMA_CPP: {
            "formats": ["GGUF", "GGML"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.VULKAN, AccelerationBackend.OPENCL],
            "min_ram_mb": 512,
            "recommended_ram_mb": 4096,
            "quantization_support": True,
            "streaming": True,
            "model_types": ["LLM"],
            "android_support": "excellent",
            "termux_compatible": True,
            "performance_cpu": 0.9,
            "performance_gpu": 0.7,
            "memory_efficiency": 0.95,
            "battery_efficiency": 0.85,
            "ease_score": 0.9
        },
        RuntimeType.ONNX_RUNTIME: {
            "formats": ["ONNX"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.NNAPI, AccelerationBackend.OPENCL],
            "min_ram_mb": 256,
            "recommended_ram_mb": 2048,
            "quantization_support": True,
            "streaming": False,
            "model_types": ["LLM", "Vision", "Speech", "General ML"],
            "android_support": "good",
            "termux_compatible": True,
            "performance_cpu": 0.75,
            "performance_gpu": 0.6,
            "memory_efficiency": 0.8,
            "battery_efficiency": 0.75,
            "ease_score": 0.85
        },
        RuntimeType.EXECUTORCH: {
            "formats": ["PT2", "ONNX"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.NNAPI, AccelerationBackend.HEXAGON_DSP],
            "min_ram_mb": 128,
            "recommended_ram_mb": 1024,
            "quantization_support": True,
            "streaming": True,
            "model_types": ["LLM", "Vision", "Speech"],
            "android_support": "excellent",
            "termux_compatible": False,
            "performance_cpu": 0.85,
            "performance_gpu": 0.7,
            "memory_efficiency": 0.9,
            "battery_efficiency": 0.9,
            "ease_score": 0.6
        },
        RuntimeType.MLC_LLM: {
            "formats": ["MLC"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.VULKAN, AccelerationBackend.OPENCL],
            "min_ram_mb": 1024,
            "recommended_ram_mb": 6144,
            "quantization_support": True,
            "streaming": True,
            "model_types": ["LLM"],
            "android_support": "good",
            "termux_compatible": False,
            "performance_cpu": 0.8,
            "performance_gpu": 0.9,
            "memory_efficiency": 0.75,
            "battery_efficiency": 0.7,
            "ease_score": 0.5
        },
        RuntimeType.LITERT: {
            "formats": ["TFLITE", "BIN"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.NNAPI, AccelerationBackend.HEXAGON_DSP],
            "min_ram_mb": 256,
            "recommended_ram_mb": 2048,
            "quantization_support": True,
            "streaming": False,
            "model_types": ["LLM", "General ML"],
            "android_support": "excellent",
            "termux_compatible": False,
            "performance_cpu": 0.7,
            "performance_gpu": 0.8,
            "memory_efficiency": 0.85,
            "battery_efficiency": 0.85,
            "ease_score": 0.7
        },
        RuntimeType.TFLITE: {
            "formats": ["TFLITE"],
            "backends": [AccelerationBackend.CPU, AccelerationBackend.NNAPI, AccelerationBackend.HEXAGON_DSP],
            "min_ram_mb": 128,
            "recommended_ram_mb": 1024,
            "quantization_support": True,
            "streaming": False,
            "model_types": ["Vision", "Speech", "General ML"],
            "android_support": "excellent",
            "termux_compatible": False,
            "performance_cpu": 0.65,
            "performance_gpu": 0.75,
            "memory_efficiency": 0.9,
            "battery_efficiency": 0.85,
            "ease_score": 0.8
        }
    }
    
    def __init__(self, hardware_info: Dict[str, Any]):
        self.hardware = hardware_info
        self.scores: List[RuntimeScore] = []
        
    def _get_available_ram(self) -> int:
        """Get available RAM in MB."""
        return self.hardware.get("memory", {}).get("ram", {}).get("available", 2048)
    
    def _get_total_ram(self) -> int:
        """Get total RAM in MB."""
        return self.hardware.get("memory", {}).get("ram", {}).get("total", 4096)
    
    def _has_vulkan(self) -> bool:
        """Check Vulkan support."""
        return self.hardware.get("gpu", {}).get("vulkan_support", False)
    
    def _has_opencl(self) -> bool:
        """Check OpenCL support."""
        return self.hardware.get("gpu", {}).get("opencl_support", False)
    
    def _has_hexagon(self) -> bool:
        """Check Hexagon DSP support."""
        return self.hardware.get("npu", {}).get("hexagon_dsp", False)
    
    def _is_termux(self) -> bool:
        """Check if running in Termux."""
        return self.hardware.get("device", {}).get("termux", False)
    
    def _check_library_exists(self, lib_paths: List[str]) -> bool:
        """Check if library exists on system."""
        return any(os.path.exists(p) for p in lib_paths)
    
    def score_runtime(self, runtime: RuntimeType) -> RuntimeScore:
        """Calculate comprehensive score for a runtime."""
        caps = self.RUNTIME_CAPABILITIES[runtime]
        score = RuntimeScore(runtime=runtime)
        
        available_ram = self._get_available_ram()
        total_ram = self._get_total_ram()
        
        # Compatibility Score (0-1)
        compat_score = 1.0
        
        # Check RAM requirements
        if available_ram < caps["min_ram_mb"]:
            compat_score *= 0.3
            score.reasons.append(f"Low RAM: {available_ram}MB < {caps['min_ram_mb']}MB minimum")
        elif available_ram < caps["recommended_ram_mb"]:
            compat_score *= 0.7
            score.reasons.append(f"RAM below recommended: {available_ram}MB < {caps['recommended_ram_mb']}MB")
        
        # Check Termux compatibility
        if not caps["termux_compatible"] and self._is_termux():
            compat_score *= 0.5
            score.reasons.append(f"Not Termux-compatible: {runtime.value}")
        
        # Check backend availability
        has_suitable_backend = False
        for backend in caps["backends"]:
            if backend == AccelerationBackend.CPU:
                has_suitable_backend = True
            elif backend == AccelerationBackend.VULKAN and self._has_vulkan():
                has_suitable_backend = True
            elif backend == AccelerationBackend.OPENCL and self._has_opencl():
                has_suitable_backend = True
            elif backend == AccelerationBackend.HEXAGON_DSP and self._has_hexagon():
                has_suitable_backend = True
            elif backend == AccelerationBackend.NNAPI:
                has_suitable_backend = True  # NNAPI always available on Android
        
        if not has_suitable_backend:
            compat_score *= 0.4
            score.reasons.append("No suitable acceleration backend available")
        
        score.compatibility_score = compat_score
        
        # Performance Score (0-1)
        perf_score = caps["performance_cpu"]  # Base on CPU
        
        # Boost for GPU acceleration if available
        if self._has_vulkan() and AccelerationBackend.VULKAN in caps["backends"]:
            perf_score = max(perf_score, caps["performance_gpu"] * 1.1)
            score.reasons.append("Vulkan acceleration available")
        
        if self._has_opencl() and AccelerationBackend.OPENCL in caps["backends"]:
            perf_score = max(perf_score, caps["performance_gpu"] * 1.05)
            score.reasons.append("OpenCL acceleration available")
        
        if self._has_hexagon() and AccelerationBackend.HEXAGON_DSP in caps["backends"]:
            perf_score *= 1.2
            score.reasons.append("Hexagon DSP available for AI acceleration")
        
        score.performance_score = min(perf_score, 1.0)
        
        # Memory Efficiency (0-1)
        score.memory_efficiency = caps["memory_efficiency"]
        
        # Battery Efficiency (0-1)
        score.battery_efficiency = caps["battery_efficiency"]
        
        # Model Support (0-1) - LLM-focused for FlowCore
        if "LLM" in caps["model_types"]:
            score.model_support = 1.0
        else:
            score.model_support = 0.5
        
        # Ease of Use (0-1)
        score.ease_of_use = caps["ease_score"]
        
        # Calculate Total Score with weights
        # For FlowCore: Performance > Memory > Battery > Ease
        score.total_score = (
            score.performance_score * 0.30 +
            score.compatibility_score * 0.25 +
            score.memory_efficiency * 0.20 +
            score.battery_efficiency * 0.15 +
            score.model_support * 0.05 +
            score.ease_of_use * 0.05
        )
        
        return score
    
    def select_best_runtime(self) -> RuntimeScore:
        """Evaluate all runtimes and select the best one."""
        self.scores = []
        
        for runtime in RuntimeType:
            score = self.score_runtime(runtime)
            self.scores.append(score)
        
        # Sort by total score descending
        self.scores.sort(key=lambda s: s.total_score, reverse=True)
        
        # Mark top choice as recommended
        if self.scores:
            self.scores[0].recommended = True
            
            # Add specific recommendation reason
            if self.scores[0].runtime == RuntimeType.LLAMA_CPP:
                self.scores[0].reasons.insert(0, "BEST CHOICE: Excellent GGUF support, optimal for local LLM inference")
            elif self.scores[0].runtime == RuntimeType.ONNX_RUNTIME:
                self.scores[0].reasons.insert(0, "RECOMMENDED: Great versatility, good Android support")
        
        return self.scores[0] if self.scores else None
    
    def get_installation_commands(self, runtime: RuntimeType) -> List[str]:
        """Get installation commands for selected runtime."""
        commands = {
            RuntimeType.LLAMA_CPP: [
                "# Install llama.cpp in Termux",
                "pkg update && pkg upgrade",
                "pkg install git cmake clang python",
                "cd /tmp && git clone https://github.com/ggerganov/llama.cpp",
                "cd llama.cpp && make -j$(nproc)",
                "# Or use pip for Python bindings",
                "pip install llama-cpp-python"
            ],
            RuntimeType.ONNX_RUNTIME: [
                "# Install ONNX Runtime",
                "pip install onnxruntime",
                "# For mobile: onnxruntime-mobile",
                "pip install onnxruntime-mobile"
            ],
            RuntimeType.EXECUTORCH: [
                "# ExecuTorch requires PyTorch build",
                "pip install executorch",
                "# Note: May require custom build for Android"
            ],
            RuntimeType.MLC_LLM: [
                "# MLC LLM installation",
                "pip install mlc-ai-nightly",
                "pip install mlc-chat-nightly",
                "# Requires Vulkan support for GPU acceleration"
            ],
            RuntimeType.LITERT: [
                "# LiteRT (TensorFlow Lite)",
                "pip install tflite-runtime",
                "# Or use TensorFlow Lite libraries"
            ],
            RuntimeType.TFLITE: [
                "# TensorFlow Lite",
                "pip install tensorflow-lite"
            ]
        }
        return commands.get(runtime, [])
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive runtime selection report."""
        best = self.select_best_runtime()
        
        report = {
            "hardware_summary": {
                "total_ram_mb": self._get_total_ram(),
                "available_ram_mb": self._get_available_ram(),
                "vulkan_support": self._has_vulkan(),
                "opencl_support": self._has_opencl(),
                "hexagon_dsp": self._has_hexagon(),
                "termux": self._is_termux()
            },
            "runtime_scores": [
                {
                    "runtime": s.runtime.value,
                    "total_score": round(s.total_score, 3),
                    "compatibility": round(s.compatibility_score, 3),
                    "performance": round(s.performance_score, 3),
                    "memory_efficiency": round(s.memory_efficiency, 3),
                    "battery_efficiency": round(s.battery_efficiency, 3),
                    "recommended": s.recommended
                }
                for s in self.scores
            ],
            "recommendation": {
                "runtime": best.runtime.value if best else None,
                "score": round(best.total_score, 3) if best else 0,
                "reasons": best.reasons if best else [],
                "installation": self.get_installation_commands(best.runtime) if best else []
            }
        }
        
        return report
    
    def print_recommendation(self):
        """Print human-readable recommendation."""
        best = self.select_best_runtime()
        
        print("=" * 60)
        print("FLOWCORE RUNTIME SELECTION REPORT")
        print("=" * 60)
        print(f"\nHardware Profile:")
        print(f"  RAM: {self._get_available_ram()}MB available / {self._get_total_ram()}MB total")
        print(f"  Vulkan: {'Yes' if self._has_vulkan() else 'No'}")
        print(f"  OpenCL: {'Yes' if self._has_opencl() else 'No'}")
        print(f"  Hexagon DSP: {'Yes' if self._has_hexagon() else 'No'}")
        print(f"  Termux: {'Yes' if self._is_termux() else 'No'}")
        print("\n" + "-" * 60)
        print("\nRuntime Rankings:")
        print("-" * 60)
        
        for i, score in enumerate(self.scores, 1):
            marker = "★ RECOMMENDED" if score.recommended else ""
            print(f"{i}. {score.runtime.value:20} Score: {score.total_score:.3f} {marker}")
        
        if best:
            print("\n" + "=" * 60)
            print(f"RECOMMENDATION: {best.runtime.value}")
            print("=" * 60)
            print("\nReasons:")
            for reason in best.reasons:
                print(f"  • {reason}")
            
            print("\nInstallation Commands:")
            for cmd in self.get_installation_commands(best.runtime):
                print(f"  {cmd}")
        
        print("=" * 60)


if __name__ == "__main__":
    # Example usage with sample hardware data
    sample_hardware = {
        "device": {"termux": True},
        "memory": {
            "ram": {"total": 8192, "available": 4096},
            "zram": {"active": True, "total": 4096}
        },
        "gpu": {
            "vulkan_support": True,
            "opencl_support": False
        },
        "npu": {
            "present": True,
            "hexagon_dsp": True
        }
    }
    
    selector = RuntimeSelector(sample_hardware)
    selector.print_recommendation()
    
    # Save report
    report = selector.generate_report()
    with open("/workspace/FlowCore/Logs/runtime_selection.json", "w") as f:
        json.dump(report, f, indent=2)

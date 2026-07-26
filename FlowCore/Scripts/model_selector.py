#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowCore Model Selector v1.0
Mission 3: Compare and Select Best LLM Model for Hardware

Compares: Phi-3 Mini, Qwen 2.5, Gemma, SmolLM, TinyLlama, Llama 3.2, DeepSeek Lite
Selects optimal model based on RAM, speed, tokens/s, consumption, latency, precision.
"""

import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ModelFamily(Enum):
    PHI = "phi"
    QWEN = "qwen"
    GEMMA = "gemma"
    SMOLLM = "smollm"
    TINYLLAMA = "tinyllama"
    LLAMA = "llama"
    DEEPSEEK = "deepseek"


@dataclass
class ModelSpec:
    """Specification for an LLM model."""
    name: str
    family: ModelFamily
    params_billions: float
    quantized_sizes: Dict[str, int]  # quantization -> size in MB
    min_ram_gb: float
    recommended_ram_gb: float
    context_length: int
    architecture: str
    license: str
    strengths: List[str]
    weaknesses: List[str]
    
    # Performance estimates (tokens/sec on mid-range mobile CPU)
    performance_q4: float  # tokens/sec at Q4_K_M
    performance_q5: float  # tokens/sec at Q5_K_M
    performance_q8: float  # tokens/sec at Q8_0
    
    # Quality scores (0-1)
    reasoning_score: float
    coding_score: float
    multilingual_score: float
    instruction_following: float
    
    # Efficiency scores (0-1)
    memory_efficiency: float
    battery_efficiency: float
    startup_speed: float


# Model database with technical specifications
MODEL_DATABASE = [
    ModelSpec(
        name="Phi-3-mini-4k-instruct",
        family=ModelFamily.PHI,
        params_billions=3.8,
        quantized_sizes={"Q4_K_M": 2400, "Q5_K_M": 2800, "Q6_K": 3200, "Q8_0": 4100},
        min_ram_gb=4.0,
        recommended_ram_gb=6.0,
        context_length=4096,
        architecture="Transformer decoder-only",
        license="MIT",
        strengths=["Excellent reasoning for size", "Fast inference", "Good instruction following", "Microsoft quality"],
        weaknesses=["Limited context window", "Less multilingual", "Smaller knowledge base"],
        performance_q4=35.0,
        performance_q5=30.0,
        performance_q8=22.0,
        reasoning_score=0.85,
        coding_score=0.70,
        multilingual_score=0.50,
        instruction_following=0.88,
        memory_efficiency=0.92,
        battery_efficiency=0.88,
        startup_speed=0.90
    ),
    ModelSpec(
        name="Phi-3.5-mini-instruct",
        family=ModelFamily.PHI,
        params_billions=3.8,
        quantized_sizes={"Q4_K_M": 2500, "Q5_K_M": 2900, "Q6_K": 3300, "Q8_0": 4200},
        min_ram_gb=4.0,
        recommended_ram_gb=6.0,
        context_length=128000,
        architecture="Transformer decoder-only",
        license="MIT",
        strengths=["Extended context", "Improved reasoning", "Better than Phi-3", "Great value"],
        weaknesses=["Still limited multilingual", "Large context uses more RAM"],
        performance_q4=33.0,
        performance_q5=28.0,
        performance_q8=20.0,
        reasoning_score=0.88,
        coding_score=0.72,
        multilingual_score=0.55,
        instruction_following=0.90,
        memory_efficiency=0.88,
        battery_efficiency=0.85,
        startup_speed=0.85
    ),
    ModelSpec(
        name="Qwen2.5-3B-Instruct",
        family=ModelFamily.QWEN,
        params_billions=3.0,
        quantized_sizes={"Q4_K_M": 2000, "Q5_K_M": 2300, "Q6_K": 2600, "Q8_0": 3400},
        min_ram_gb=3.0,
        recommended_ram_gb=5.0,
        context_length=32768,
        architecture="Transformer decoder-only",
        license="Apache 2.0",
        strengths=["Excellent multilingual", "Strong coding", "Alibaba quality", "Good balance"],
        weaknesses=["Slightly slower than Phi", "Less known in Western markets"],
        performance_q4=32.0,
        performance_q5=27.0,
        performance_q8=19.0,
        reasoning_score=0.82,
        coding_score=0.80,
        multilingual_score=0.90,
        instruction_following=0.85,
        memory_efficiency=0.90,
        battery_efficiency=0.87,
        startup_speed=0.88
    ),
    ModelSpec(
        name="Qwen2.5-7B-Instruct",
        family=ModelFamily.QWEN,
        params_billions=7.0,
        quantized_sizes={"Q4_K_M": 4200, "Q5_K_M": 4900, "Q6_K": 5600, "Q8_0": 7200},
        min_ram_gb=6.0,
        recommended_ram_gb=8.0,
        context_length=32768,
        architecture="Transformer decoder-only",
        license="Apache 2.0",
        strengths=["Excellent all-rounder", "Strong reasoning", "Great coding", "Multilingual"],
        weaknesses=["Requires more RAM", "Slower on low-end devices"],
        performance_q4=22.0,
        performance_q5=18.0,
        performance_q8=13.0,
        reasoning_score=0.90,
        coding_score=0.88,
        multilingual_score=0.92,
        instruction_following=0.90,
        memory_efficiency=0.78,
        battery_efficiency=0.75,
        startup_speed=0.75
    ),
    ModelSpec(
        name="Gemma-2-2b-it",
        family=ModelFamily.GEMMA,
        params_billions=2.5,
        quantized_sizes={"Q4_K_M": 1600, "Q5_K_M": 1900, "Q6_K": 2100, "Q8_0": 2800},
        min_ram_gb=3.0,
        recommended_ram_gb=4.0,
        context_length=8192,
        architecture="Transformer decoder-only",
        license="Gemma Terms",
        strengths=["Very fast", "Google quality", "Efficient", "Good for chat"],
        weaknesses=["Smaller context", "License restrictions", "Less capable than larger models"],
        performance_q4=42.0,
        performance_q5=37.0,
        performance_q8=28.0,
        reasoning_score=0.75,
        coding_score=0.65,
        multilingual_score=0.70,
        instruction_following=0.82,
        memory_efficiency=0.95,
        battery_efficiency=0.92,
        startup_speed=0.95
    ),
    ModelSpec(
        name="Gemma-2-9b-it",
        family=ModelFamily.GEMMA,
        params_billions=9.0,
        quantized_sizes={"Q4_K_M": 5500, "Q5_K_M": 6400, "Q6_K": 7200, "Q8_0": 9500},
        min_ram_gb=8.0,
        recommended_ram_gb=12.0,
        context_length=8192,
        architecture="Transformer decoder-only",
        license="Gemma Terms",
        strengths=["High quality outputs", "Google research", "Good reasoning", "Creative"],
        weaknesses=["High RAM requirement", "Slow on mobile", "License concerns"],
        performance_q4=15.0,
        performance_q5=12.0,
        performance_q8=8.0,
        reasoning_score=0.88,
        coding_score=0.82,
        multilingual_score=0.78,
        instruction_following=0.87,
        memory_efficiency=0.65,
        battery_efficiency=0.62,
        startup_speed=0.60
    ),
    ModelSpec(
        name="SmolLM-1.7B-Instruct",
        family=ModelFamily.SMOLLM,
        params_billions=1.7,
        quantized_sizes={"Q4_K_M": 1100, "Q5_K_M": 1300, "Q6_K": 1500, "Q8_0": 2000},
        min_ram_gb=2.0,
        recommended_ram_gb=3.0,
        context_length=4096,
        architecture="Transformer decoder-only",
        license="Apache 2.0",
        strengths=["Ultra-fast", "Minimal RAM", "Good for simple tasks", "Open license"],
        weaknesses=["Limited capabilities", "Not good for complex reasoning", "Small knowledge"],
        performance_q4=55.0,
        performance_q5=48.0,
        performance_q8=38.0,
        reasoning_score=0.60,
        coding_score=0.50,
        multilingual_score=0.45,
        instruction_following=0.75,
        memory_efficiency=0.98,
        battery_efficiency=0.95,
        startup_speed=0.98
    ),
    ModelSpec(
        name="SmolLM-3.6B-Instruct",
        family=ModelFamily.SMOLLM,
        params_billions=3.6,
        quantized_sizes={"Q4_K_M": 2300, "Q5_K_M": 2700, "Q6_K": 3100, "Q8_0": 4000},
        min_ram_gb=4.0,
        recommended_ram_gb=6.0,
        context_length=4096,
        architecture="Transformer decoder-only",
        license="Apache 2.0",
        strengths=["Fast", "Better than 1.7B", "Good balance", "Open license"],
        weaknesses=["Still limited vs larger models", "Small context"],
        performance_q4=38.0,
        performance_q5=33.0,
        performance_q8=25.0,
        reasoning_score=0.72,
        coding_score=0.62,
        multilingual_score=0.55,
        instruction_following=0.80,
        memory_efficiency=0.90,
        battery_efficiency=0.88,
        startup_speed=0.92
    ),
    ModelSpec(
        name="TinyLlama-1.1B-Chat",
        family=ModelFamily.TINYLLAMA,
        params_billions=1.1,
        quantized_sizes={"Q4_K_M": 700, "Q5_K_M": 850, "Q6_K": 1000, "Q8_0": 1300},
        min_ram_gb=1.5,
        recommended_ram_gb=2.5,
        context_length=2048,
        architecture="Llama-based",
        license="Apache 2.0",
        strengths=["Extremely small", "Very fast", "Llama-compatible", "Low power"],
        weaknesses=["Limited capabilities", "Very small context", "Outdated training"],
        performance_q4=65.0,
        performance_q5=58.0,
        performance_q8=45.0,
        reasoning_score=0.55,
        coding_score=0.45,
        multilingual_score=0.50,
        instruction_following=0.70,
        memory_efficiency=0.99,
        battery_efficiency=0.97,
        startup_speed=0.99
    ),
    ModelSpec(
        name="Llama-3.2-3B-Instruct",
        family=ModelFamily.LLAMA,
        params_billions=3.0,
        quantized_sizes={"Q4_K_M": 2000, "Q5_K_M": 2350, "Q6_K": 2700, "Q8_0": 3500},
        min_ram_gb=4.0,
        recommended_ram_gb=6.0,
        context_length=8192,
        architecture="Transformer decoder-only",
        license="Llama Community",
        strengths=["Meta quality", "Well-tested", "Good ecosystem", "Balanced"],
        weaknesses=["License requires approval", "Not as efficient as Phi"],
        performance_q4=34.0,
        performance_q5=29.0,
        performance_q8=21.0,
        reasoning_score=0.83,
        coding_score=0.75,
        multilingual_score=0.65,
        instruction_following=0.86,
        memory_efficiency=0.88,
        battery_efficiency=0.85,
        startup_speed=0.87
    ),
    ModelSpec(
        name="Llama-3.2-1B-Instruct",
        family=ModelFamily.LLAMA,
        params_billions=1.0,
        quantized_sizes={"Q4_K_M": 650, "Q5_K_M": 800, "Q6_K": 950, "Q8_0": 1250},
        min_ram_gb=1.5,
        recommended_ram_gb=2.5,
        context_length=8192,
        architecture="Transformer decoder-only",
        license="Llama Community",
        strengths=["Smallest Llama", "Fast", "Meta ecosystem", "Good for simple tasks"],
        weaknesses=["Very limited capabilities", "License concerns"],
        performance_q4=60.0,
        performance_q5=53.0,
        performance_q8=42.0,
        reasoning_score=0.58,
        coding_score=0.48,
        multilingual_score=0.52,
        instruction_following=0.72,
        memory_efficiency=0.98,
        battery_efficiency=0.96,
        startup_speed=0.98
    ),
    ModelSpec(
        name="DeepSeek-R1-Distill-Qwen-1.5B",
        family=ModelFamily.DEEPSEEK,
        params_billions=1.5,
        quantized_sizes={"Q4_K_M": 950, "Q5_K_M": 1150, "Q6_K": 1350, "Q8_0": 1800},
        min_ram_gb=2.0,
        recommended_ram_gb=3.5,
        context_length=8192,
        architecture="Transformer decoder-only",
        license="MIT",
        strengths=["Reasoning-focused", "Distilled from large model", "Efficient", "Open license"],
        weaknesses=["Newer model less tested", "Smaller community"],
        performance_q4=50.0,
        performance_q5=44.0,
        performance_q8=35.0,
        reasoning_score=0.78,
        coding_score=0.68,
        multilingual_score=0.70,
        instruction_following=0.82,
        memory_efficiency=0.94,
        battery_efficiency=0.92,
        startup_speed=0.94
    ),
    ModelSpec(
        name="DeepSeek-R1-Distill-Qwen-7B",
        family=ModelFamily.DEEPSEEK,
        params_billions=7.0,
        quantized_sizes={"Q4_K_M": 4300, "Q5_K_M": 5000, "Q6_K": 5700, "Q8_0": 7500},
        min_ram_gb=6.0,
        recommended_ram_gb=10.0,
        context_length=32768,
        architecture="Transformer decoder-only",
        license="MIT",
        strengths=["Excellent reasoning", "Large context", "Quality rivaling bigger models"],
        weaknesses=["High RAM needs", "Slower on mobile"],
        performance_q4=20.0,
        performance_q5=17.0,
        performance_q8=12.0,
        reasoning_score=0.92,
        coding_score=0.85,
        multilingual_score=0.88,
        instruction_following=0.90,
        memory_efficiency=0.75,
        battery_efficiency=0.72,
        startup_speed=0.70
    )
]


@dataclass
class ModelScore:
    """Score for a model on specific hardware."""
    model: ModelSpec
    total_score: float = 0.0
    hardware_compatibility: float = 0.0
    performance_score: float = 0.0
    quality_score: float = 0.0
    efficiency_score: float = 0.0
    recommended_quantization: str = ""
    estimated_tokens_per_sec: float = 0.0
    estimated_ram_usage_mb: int = 0
    reasons: List[str] = field(default_factory=list)
    recommended: bool = False


class ModelSelector:
    """Intelligent LLM model selector based on hardware and use case."""
    
    def __init__(self, hardware_info: Dict[str, Any], use_case: str = "general"):
        self.hardware = hardware_info
        self.use_case = use_case  # general, coding, chat, reasoning, multilingual
        self.scores: List[ModelScore] = []
        
        # Use case weights
        self.use_case_weights = {
            "general": {"quality": 0.35, "performance": 0.30, "efficiency": 0.25, "compatibility": 0.10},
            "coding": {"quality": 0.40, "performance": 0.25, "efficiency": 0.20, "compatibility": 0.15},
            "chat": {"quality": 0.30, "performance": 0.35, "efficiency": 0.25, "compatibility": 0.10},
            "reasoning": {"quality": 0.45, "performance": 0.25, "efficiency": 0.20, "compatibility": 0.10},
            "multilingual": {"quality": 0.40, "performance": 0.25, "efficiency": 0.20, "compatibility": 0.15}
        }
    
    def _get_available_ram_mb(self) -> int:
        """Get available RAM in MB."""
        return self.hardware.get("memory", {}).get("ram", {}).get("available", 4096)
    
    def _get_total_ram_mb(self) -> int:
        """Get total RAM in MB."""
        return self.hardware.get("memory", {}).get("ram", {}).get("total", 8192)
    
    def _select_quantization(self, model: ModelSpec) -> tuple:
        """Select best quantization level for available RAM."""
        available = self._get_available_ram_mb()
        # Reserve 30% of available RAM for context, overhead
        usable_ram = int(available * 0.7)
        
        # Priority order: Q4 > Q5 > Q6 > Q8 (prefer smaller for mobile)
        quant_order = ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
        
        for quant in quant_order:
            if quant in model.quantized_sizes:
                size = model.quantized_sizes[quant]
                if size <= usable_ram:
                    return quant, size
        
        # If none fit, return smallest
        smallest = min(model.quantized_sizes.items(), key=lambda x: x[1])
        return smallest[0], smallest[1]
    
    def score_model(self, model: ModelSpec) -> ModelScore:
        """Calculate comprehensive score for a model."""
        score = ModelScore(model=model)
        
        available_ram = self._get_available_ram_mb()
        total_ram = self._get_total_ram_mb()
        
        # Select quantization
        quant, size_mb = self._select_quantization(model)
        score.recommended_quantization = quant
        score.estimated_ram_usage_mb = size_mb
        
        # Hardware Compatibility (0-1)
        compat = 1.0
        if size_mb > available_ram * 0.8:
            compat *= 0.3
            score.reasons.append(f"Model too large for available RAM ({size_mb}MB > {int(available_ram * 0.8)}MB)")
        elif size_mb > available_ram * 0.5:
            compat *= 0.6
            score.reasons.append(f"Model uses significant portion of RAM")
        
        # Check minimum RAM requirement
        if total_ram < model.min_ram_gb * 1024:
            compat *= 0.4
            score.reasons.append(f"Below minimum RAM requirement ({model.min_ram_gb}GB)")
        
        score.hardware_compatibility = compat
        
        # Performance Score (0-1)
        perf_map = {"Q4_K_M": model.performance_q4, "Q5_K_M": model.performance_q5, "Q8_0": model.performance_q8}
        est_tps = perf_map.get(quant, model.performance_q4)
        score.estimated_tokens_per_sec = est_tps
        
        # Normalize to 0-1 (assuming 60 TPS is excellent)
        score.performance_score = min(est_tps / 60.0, 1.0)
        
        # Quality Score (0-1) - weighted by use case
        weights = self.use_case_weights.get(self.use_case, self.use_case_weights["general"])
        
        quality_components = {
            "reasoning": model.reasoning_score,
            "coding": model.coding_score,
            "multilingual": model.multilingual_score,
            "instruction": model.instruction_following
        }
        
        if self.use_case == "coding":
            quality = (model.reasoning_score * 0.3 + model.coding_score * 0.4 + 
                      model.multilingual_score * 0.1 + model.instruction_following * 0.2)
        elif self.use_case == "multilingual":
            quality = (model.reasoning_score * 0.2 + model.coding_score * 0.2 + 
                      model.multilingual_score * 0.4 + model.instruction_following * 0.2)
        else:
            quality = (model.reasoning_score * 0.3 + model.coding_score * 0.2 + 
                      model.multilingual_score * 0.2 + model.instruction_following * 0.3)
        
        score.quality_score = quality
        
        # Efficiency Score (0-1)
        score.efficiency_score = (model.memory_efficiency * 0.4 + 
                                  model.battery_efficiency * 0.4 + 
                                  model.startup_speed * 0.2)
        
        # Calculate Total Score
        score.total_score = (
            score.quality_score * weights["quality"] +
            score.performance_score * weights["performance"] +
            score.efficiency_score * weights["efficiency"] +
            score.hardware_compatibility * weights["compatibility"]
        )
        
        return score
    
    def select_best_model(self) -> ModelScore:
        """Evaluate all models and select the best one."""
        self.scores = []
        
        for model in MODEL_DATABASE:
            score = self.score_model(model)
            self.scores.append(score)
        
        # Sort by total score descending
        self.scores.sort(key=lambda s: s.total_score, reverse=True)
        
        # Mark top choice as recommended
        if self.scores:
            self.scores[0].recommended = True
            self.scores[0].reasons.insert(0, f"BEST FOR {self.use_case.upper()}")
        
        return self.scores[0] if self.scores else None
    
    def get_download_url(self, model_name: str, quantization: str) -> str:
        """Generate HuggingFace download URL for model."""
        model_urls = {
            "Phi-3-mini-4k-instruct": f"microsoft/Phi-3-mini-4k-instruct-gguf/{quantization}.gguf",
            "Phi-3.5-mini-instruct": f"microsoft/Phi-3.5-mini-instruct-gguf/{quantization}.gguf",
            "Qwen2.5-3B-Instruct": f"Qwen/Qwen2.5-3B-Instruct-GGUF/{quantization}.gguf",
            "Qwen2.5-7B-Instruct": f"Qwen/Qwen2.5-7B-Instruct-GGUF/{quantization}.gguf",
            "Gemma-2-2b-it": f"google/gemma-2-2b-it-GGUF/{quantization}.gguf",
            "Gemma-2-9b-it": f"google/gemma-2-9b-it-GGUF/{quantization}.gguf",
            "SmolLM-1.7B-Instruct": f"HuggingFaceTB/SmolLM-1.7B-Instruct-GGUF/{quantization}.gguf",
            "SmolLM-3.6B-Instruct": f"HuggingFaceTB/SmolLM-3.6B-Instruct-GGUF/{quantization}.gguf",
            "TinyLlama-1.1B-Chat": f"TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/{quantization}.gguf",
            "Llama-3.2-3B-Instruct": f"meta-llama/Llama-3.2-3B-Instruct-GGUF/{quantization}.gguf",
            "Llama-3.2-1B-Instruct": f"meta-llama/Llama-3.2-1B-Instruct-GGUF/{quantization}.gguf",
            "DeepSeek-R1-Distill-Qwen-1.5B": f"deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/{quantization}.gguf",
            "DeepSeek-R1-Distill-Qwen-7B": f"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF/{quantization}.gguf"
        }
        base_url = "https://huggingface.co/"
        path = model_urls.get(model_name, "")
        return f"{base_url}{path}" if path else ""
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive model selection report."""
        best = self.select_best_model()
        
        report = {
            "hardware_profile": {
                "available_ram_mb": self._get_available_ram_mb(),
                "total_ram_mb": self._get_total_ram_mb(),
                "use_case": self.use_case
            },
            "model_scores": [
                {
                    "name": s.model.name,
                    "params_b": s.model.params_billions,
                    "total_score": round(s.total_score, 3),
                    "quantization": s.recommended_quantization,
                    "size_mb": s.estimated_ram_usage_mb,
                    "tokens_per_sec": round(s.estimated_tokens_per_sec, 1),
                    "quality": round(s.quality_score, 3),
                    "performance": round(s.performance_score, 3),
                    "efficiency": round(s.efficiency_score, 3),
                    "recommended": s.recommended
                }
                for s in self.scores[:10]  # Top 10
            ],
            "recommendation": {
                "model": best.model.name if best else None,
                "family": best.model.family.value if best else None,
                "quantization": best.recommended_quantization if best else None,
                "estimated_size_mb": best.estimated_ram_usage_mb if best else 0,
                "estimated_tokens_per_sec": round(best.estimated_tokens_per_sec, 1) if best else 0,
                "download_url": self.get_download_url(best.model.name, best.recommended_quantization) if best else "",
                "reasons": best.reasons if best else [],
                "strengths": best.model.strengths if best else [],
                "license": best.model.license if best else "Unknown"
            }
        }
        
        return report
    
    def print_recommendation(self):
        """Print human-readable recommendation."""
        best = self.select_best_model()
        
        print("=" * 70)
        print(f"FLOWCORE MODEL SELECTION REPORT - Use Case: {self.use_case.upper()}")
        print("=" * 70)
        print(f"\nHardware Profile:")
        print(f"  Available RAM: {self._get_available_ram_mb()}MB")
        print(f"  Total RAM: {self._get_total_ram_mb()}MB")
        print("\n" + "-" * 70)
        print("\nTop 5 Models:")
        print("-" * 70)
        print(f"{'Rank':<5} {'Model':<30} {'Size':<10} {'TPS':<8} {'Score':<8}")
        print("-" * 70)
        
        for i, score in enumerate(self.scores[:5], 1):
            marker = "★" if score.recommended else " "
            print(f"{marker}{i:<4} {score.model.name:<30} {score.estimated_ram_usage_mb:<10}MB {score.estimated_tokens_per_sec:<8.1f} {score.total_score:.3f}")
        
        if best:
            print("\n" + "=" * 70)
            print(f"★ RECOMMENDED: {best.model.name}")
            print("=" * 70)
            print(f"\nQuantization: {best.recommended_quantization}")
            print(f"Estimated Size: {best.estimated_ram_usage_mb}MB")
            print(f"Expected Speed: {best.estimated_tokens_per_sec:.1f} tokens/sec")
            print(f"License: {best.model.license}")
            
            print("\nReasons:")
            for reason in best.reasons:
                print(f"  • {reason}")
            
            print("\nStrengths:")
            for strength in best.model.strengths:
                print(f"  ✓ {strength}")
            
            print("\nDownload URL:")
            url = self.get_download_url(best.model.name, best.recommended_quantization)
            print(f"  {url}")
        
        print("=" * 70)


if __name__ == "__main__":
    # Example usage with sample hardware data
    sample_hardware = {
        "memory": {
            "ram": {"total": 8192, "available": 5000}
        }
    }
    
    print("\n=== GENERAL USE CASE ===\n")
    selector_general = ModelSelector(sample_hardware, use_case="general")
    selector_general.print_recommendation()
    
    print("\n\n=== CODING USE CASE ===\n")
    selector_coding = ModelSelector(sample_hardware, use_case="coding")
    selector_coding.print_recommendation()
    
    # Save reports
    report_general = selector_general.generate_report()
    with open("/workspace/FlowCore/Logs/model_selection_general.json", "w") as f:
        json.dump(report_general, f, indent=2)
    
    report_coding = selector_coding.generate_report()
    with open("/workspace/FlowCore/Logs/model_selection_coding.json", "w") as f:
        json.dump(report_coding, f, indent=2)

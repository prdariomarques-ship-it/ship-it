# FlowCore AI Engine v1.0

## Local AI Runtime for Android

**Transform your smartphone into an intelligent operating system.**

---

## 📋 Overview

FlowCore is a modular, local-first AI runtime designed for Android devices running Termux with root access. It provides:

- **Hardware Analysis**: Automatic detection of CPU, GPU, NPU, RAM, thermal sensors
- **Runtime Selection**: Intelligent selection of best AI runtime (llama.cpp, ONNX, etc.)
- **Model Management**: Download, validate, cache, and switch LLM models
- **Local Inference**: Run LLMs entirely offline
- **System Agents**: Monitor battery, temperature, performance, storage, security
- **Automation**: Rule-based automations for intelligent device management
- **Dashboard**: Real-time Rich CLI dashboard showing all metrics

---

## 🏗️ Architecture

```
FlowCore/
├── AI/
│   ├── Runtime/          # AI runtime abstractions
│   ├── Models/           # Model definitions and loaders
│   ├── Embeddings/       # Embedding generation
│   ├── Memory/           # Context and conversation memory
│   ├── Context/          # Prompt context management
│   ├── Inference/        # Inference engine
│   └── Agents/           # AI agent definitions
├── Agents/
│   └── agents.py         # System monitoring agents
├── Scripts/
│   ├── hardware_analyzer.py   # Mission 1: Hardware analysis
│   ├── runtime_selector.py    # Mission 2: Runtime selection
│   ├── model_selector.py      # Mission 3: Model selection
│   └── model_manager.py       # Mission 5: Model management
├── Services/             # Background services
├── Dashboard/            # Rich CLI dashboard
├── Benchmarks/           # Performance benchmarks
├── Tests/                # Automated tests
├── Logs/                 # Logs and reports
├── Config/               # Configuration files
└── Models/               # Downloaded models
```

---

## 🚀 Quick Start

### Prerequisites

- Android device with root (Magisk)
- Termux installed from F-Droid
- Python 3.10+ in Termux
- At least 4GB RAM (8GB recommended)

### Installation

```bash
# Update Termux packages
pkg update && pkg upgrade

# Install dependencies
pkg install python git cmake clang wget curl

# Clone FlowCore
cd ~
git clone https://github.com/your-org/flowcore.git
cd flowcore

# Install Python dependencies
pip install rich llama-cpp-python

# Run hardware analysis
python Scripts/hardware_analyzer.py

# Run runtime selector
python Scripts/runtime_selector.py

# Run model selector
python Scripts/model_selector.py
```

---

## 📊 Missions Completed

### ✅ Mission 1: Hardware Analyzer

Automatically analyzes:
- CPU cores, frequencies, governor, scheduler
- GPU capabilities (Vulkan, OpenCL)
- NPU/AI accelerators (Hexagon DSP)
- RAM, Swap, ZRAM status
- Kernel version, SELinux, Magisk
- Thermal sensors (CPU, battery, skin)
- Battery level, health, voltage
- Storage usage and filesystem

**File:** `Scripts/hardware_analyzer.py`

### ✅ Mission 2: Runtime Selector

Compares and selects optimal runtime:
- llama.cpp (Recommended for mobile)
- ONNX Runtime
- ExecuTorch
- MLC LLM
- LiteRT (TensorFlow Lite)

Scoring factors:
- Hardware compatibility
- Performance potential
- Memory efficiency
- Battery efficiency
- Model support

**File:** `Scripts/runtime_selector.py`

### ✅ Mission 3: Model Selector

Evaluates LLM models:
- Phi-3 Mini / Phi-3.5
- Qwen 2.5 (3B, 7B)
- Gemma 2 (2B, 9B)
- SmolLM (1.7B, 3.6B)
- TinyLlama (1.1B)
- Llama 3.2 (1B, 3B)
- DeepSeek R1 Distill

Selection criteria:
- Available RAM
- Expected tokens/sec
- Quality scores (reasoning, coding, multilingual)
- Efficiency (memory, battery)
- Use case optimization

**File:** `Scripts/model_selector.py`

### ✅ Mission 5: Model Manager

Features:
- Download from HuggingFace
- SHA256 hash validation
- Automatic backup before removal
- Rollback support
- Version switching
- Intelligent cache cleanup
- Usage tracking

**File:** `Scripts/model_manager.py`

### ✅ Mission 7: System Agents

Eight autonomous monitoring agents:

| Agent | Purpose | Check Interval |
|-------|---------|----------------|
| PerformanceAgent | CPU/RAM monitoring | 10s |
| BatteryAgent | Battery status | 60s |
| ThermalAgent | Temperature sensors | 15s |
| StorageAgent | Storage usage | 5min |
| SecurityAgent | Security audit | 60s |
| RootAgent | Root/Magisk status | 2min |
| NetworkAgent | Network connectivity | 30s |
| AutomationAgent | Rule orchestration | 5s |

Each agent provides:
- Real-time metrics
- Actionable recommendations
- Alert generation
- Background monitoring

**File:** `Agents/agents.py`

---

## 🔧 Configuration

Create `Config/flowcore.json`:

```json
{
  "runtime": "llama.cpp",
  "model": {
    "name": "qwen2.5-3b-instruct-q4",
    "quantization": "Q4_K_M",
    "context_length": 4096
  },
  "agents": {
    "enabled": ["PerformanceAgent", "BatteryAgent", "ThermalAgent"],
    "check_interval_multiplier": 1.0
  },
  "dashboard": {
    "refresh_rate": 2,
    "theme": "monokai"
  },
  "automation": {
    "enabled": true,
    "require_confirmation": true
  }
}
```

---

## 📈 Dashboard

The Rich CLI dashboard displays:

```
╔═══════════════════════════════════════════════════════╗
║              FLOWCORE AI ENGINE v1.0                  ║
╠═══════════════════════════════════════════════════════╣
║  DEVICE: Xiaomi X8 Pro     ANDROID: 15                ║
║  MODEL:  Qwen2.5-3B-Q4     STATUS: Ready              ║
╠═══════════════════════════════════════════════════════╣
║  CPU: ████████░░ 45%       RAM: ████░░░░░░ 3.2/8 GB  ║
║  TEMP: 38°C              BATTERY: ████████░░ 85%     ║
╠═══════════════════════════════════════════════════════╣
║  INFERENCE: 32 tokens/s   CONTEXT: 2048/4096         ║
╠═══════════════════════════════════════════════════════╣
║  AGENTS: 8 active        AUTOMATIONS: 3 rules        ║
╚═══════════════════════════════════════════════════════╝
```

---

## ⚡ Automation Examples

### High Temperature Protection

```python
{
  "name": "High Temp Protection",
  "enabled": True,
  "conditions": [
    {"metric": "cpu_temp", "operator": ">", "threshold": 50}
  ],
  "actions": [
    {"type": "notify", "message": "High temperature detected"},
    {"type": "reduce_performance", "level": "moderate"}
  ]
}
```

### Low Battery Saver

```python
{
  "name": "Low Battery Saver",
  "enabled": True,
  "conditions": [
    {"metric": "battery_level", "operator": "<", "threshold": 20}
  ],
  "actions": [
    {"type": "notify", "message": "Enable power saving mode"},
    {"type": "pause_inference", "duration": 300}
  ]
}
```

### RAM Cleanup

```python
{
  "name": "RAM Cleanup",
  "enabled": True,
  "conditions": [
    {"metric": "ram_percent", "operator": ">", "threshold": 85}
  ],
  "actions": [
    {"type": "clear_cache", "target": "model_cache"},
    {"type": "notify", "message": "Memory pressure detected"}
  ]
}
```

---

## 🔒 Security

### Safety Features

- **No destructive actions without confirmation**: Reboot, shutdown, delete operations are blocked by default
- **Hash validation**: All downloads verified with SHA256
- **Backup before removal**: Models backed up before deletion
- **SELinux awareness**: Respects Android security model
- **Root-only features**: Advanced features require explicit root

### Audit Checklist

- [ ] No hardcoded credentials
- [ ] All external inputs validated
- [ ] File operations use absolute paths
- [ ] Network requests use HTTPS
- [ ] Destructive commands blocked
- [ ] Error handling prevents crashes

---

## 📝 Logs

Logs are stored in `Logs/`:

- `hardware_report.json` - Hardware analysis results
- `runtime_selection.json` - Runtime evaluation
- `model_selection_*.json` - Model evaluations
- `agent_logs/` - Agent activity logs

---

## 🧪 Testing

Run tests:

```bash
cd Tests
python test_hardware.py
python test_runtime.py
python test_agents.py
python test_model_manager.py
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| `README.md` | This file - quick start guide |
| `INSTALL.md` | Detailed installation instructions |
| `ARCHITECTURE.md` | System architecture documentation |
| `AI_ENGINE.md` | AI inference engine details |
| `BENCHMARK.md` | Performance benchmarks |
| `SECURITY.md` | Security audit report |
| `ROADMAP.md` | Future development plans |

---

## 🎯 Recommended Configuration

For Xiaomi X8 Pro with 8GB RAM:

| Component | Recommendation |
|-----------|---------------|
| Runtime | llama.cpp |
| Model | Qwen2.5-3B-Instruct-Q4_K_M |
| Quantization | Q4_K_M (2.0GB) |
| Context | 4096 tokens |
| Expected Speed | 30-35 tokens/s |

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new features
4. Submit pull request

---

## 📄 License

MIT License - See LICENSE file

---

## ⚠️ Disclaimer

This software is provided as-is. Running AI models locally consumes significant battery and may cause device heating. Always monitor temperature and battery levels. The authors are not responsible for any damage to your device.

---

**Built with ❤️ for the Android AI community**

FlowCore AI Engine v1.0 - Transform your phone into an intelligent companion.

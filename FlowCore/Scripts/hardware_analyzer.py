#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowCore Hardware Analyzer v1.0
Mission 1: Automatic Hardware Analysis for Android/Termux

Identifies: CPU, GPU, NPU, RAM, Swap, ZRAM, Kernel, Scheduler, Governor,
Temperature, Battery, Storage, Filesystem, SELinux, Magisk
"""

import os
import re
import json
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class HardwareAnalyzer:
    """Comprehensive hardware analysis for Android devices running Termux."""
    
    def __init__(self):
        self.hardware_info: Dict[str, Any] = {}
        self.timestamp = datetime.now().isoformat()
        
    def execute_command(self, cmd: str, shell: bool = True) -> Optional[str]:
        """Execute shell command and return output."""
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None
    
    def analyze_cpu(self) -> Dict[str, Any]:
        """Analyze CPU information."""
        cpu_info = {
            "cores": 0,
            "architecture": "",
            "model": "",
            "frequencies": {},
            "governor": "",
            "scheduler": ""
        }
        
        # CPU cores
        cores = self.execute_command("nproc")
        if cores:
            cpu_info["cores"] = int(cores)
        
        # Architecture
        arch = self.execute_command("uname -m")
        if arch:
            cpu_info["architecture"] = arch
        
        # CPU model from /proc/cpuinfo
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                model_match = re.search(r"Hardware\s*:\s*(.+)", cpuinfo)
                if model_match:
                    cpu_info["model"] = model_match.group(1).strip()
        except Exception:
            pass
        
        # CPU frequencies
        freq_path = "/sys/devices/system/cpu/cpu0/cpufreq"
        if os.path.exists(freq_path):
            try:
                with open(f"{freq_path}/scaling_cur_freq", "r") as f:
                    cpu_info["frequencies"]["current"] = int(f.read().strip()) // 1000
                with open(f"{freq_path}/scaling_max_freq", "r") as f:
                    cpu_info["frequencies"]["max"] = int(f.read().strip()) // 1000
                with open(f"{freq_path}/scaling_min_freq", "r") as f:
                    cpu_info["frequencies"]["min"] = int(f.read().strip()) // 1000
            except Exception:
                pass
        
        # Governor
        governor_path = f"{freq_path}/scaling_governor"
        if os.path.exists(governor_path):
            try:
                with open(governor_path, "r") as f:
                    cpu_info["governor"] = f.read().strip()
            except Exception:
                pass
        
        # Scheduler (check one CPU as representative)
        scheduler_path = "/sys/block/mmcblk0/queue/scheduler"
        if os.path.exists(scheduler_path):
            try:
                with open(scheduler_path, "r") as f:
                    sched = f.read().strip()
                    # Active scheduler is in brackets
                    match = re.search(r"\[([^\]]+)\]", sched)
                    cpu_info["scheduler"] = match.group(1) if match else sched.split()[0]
            except Exception:
                pass
        
        return cpu_info
    
    def analyze_gpu(self) -> Dict[str, Any]:
        """Analyze GPU information."""
        gpu_info = {
            "vendor": "",
            "model": "",
            "driver": "",
            "vulkan_support": False,
            "opencl_support": False
        }
        
        # Check for Adreno (Qualcomm)
        gpu_render = self.execute_command("getprop ro.gpu.vendor")
        if gpu_render:
            gpu_info["vendor"] = gpu_render
        
        # Try to detect from EGL
        egl_vendor = self.execute_command("getprop ro.opengles.version")
        if egl_vendor:
            gpu_info["opengl_es_version"] = egl_vendor
        
        # Vulkan support
        vulkan_libs = [
            "/system/lib64/libvulkan.so",
            "/vendor/lib64/libvulkan.so",
            "/system/lib/libvulkan.so"
        ]
        gpu_info["vulkan_support"] = any(os.path.exists(lib) for lib in vulkan_libs)
        
        # OpenCL support
        opencl_libs = [
            "/system/lib64/libOpenCL.so",
            "/vendor/lib64/libOpenCL.so"
        ]
        gpu_info["opencl_support"] = any(os.path.exists(lib) for lib in opencl_libs)
        
        # For Xiaomi devices, check specific GPU
        renderer = self.execute_command("getprop ro.hardware.egl")
        if renderer:
            gpu_info["renderer"] = renderer
        
        return gpu_info
    
    def analyze_npu(self) -> Dict[str, Any]:
        """Analyze NPU/AI accelerator presence."""
        npu_info = {
            "present": False,
            "vendor": "",
            "model": "",
            "hexagon_dsp": False
        }
        
        # Check for Qualcomm Hexagon DSP
        hexagon = self.execute_command("getprop ro.vendor.qti.hw.audio")
        if hexagon or os.path.exists("/sys/module/hexagon"):
            npu_info["hexagon_dsp"] = True
            npu_info["present"] = True
            npu_info["vendor"] = "Qualcomm"
        
        # Check for other AI accelerators
        ai_props = [
            "ro.vendor.ai.engine",
            "persist.vendor.ai.engine",
            "ro.hardware.neuron"
        ]
        for prop in ai_props:
            val = self.execute_command(f"getprop {prop}")
            if val:
                npu_info["present"] = True
                npu_info["model"] = val
        
        return npu_info
    
    def analyze_memory(self) -> Dict[str, Any]:
        """Analyze RAM, Swap, and ZRAM."""
        mem_info = {
            "ram": {"total": 0, "available": 0, "used": 0},
            "swap": {"total": 0, "used": 0, "active": False},
            "zram": {"total": 0, "used": 0, "active": False, "device": ""}
        }
        
        # Parse /proc/meminfo
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
                
            for line in meminfo.split("\n"):
                if line.startswith("MemTotal:"):
                    mem_info["ram"]["total"] = int(line.split()[1]) // 1024  # MB
                elif line.startswith("MemAvailable:"):
                    mem_info["ram"]["available"] = int(line.split()[1]) // 1024
                elif line.startswith("SwapTotal:"):
                    total_swap = int(line.split()[1]) // 1024
                    mem_info["swap"]["total"] = total_swap
                    if total_swap > 0:
                        mem_info["swap"]["active"] = True
                elif line.startswith("SwapFree:"):
                    free_swap = int(line.split()[1]) // 1024
                    mem_info["swap"]["used"] = mem_info["swap"]["total"] - free_swap
        except Exception:
            pass
        
        mem_info["ram"]["used"] = mem_info["ram"]["total"] - mem_info["ram"]["available"]
        
        # Check ZRAM
        zram_devices = list(Path("/sys/block").glob("zram*"))
        if zram_devices:
            zram_dev = zram_devices[0].name
            mem_info["zram"]["device"] = zram_dev
            mem_info["zram"]["active"] = True
            
            try:
                with open(f"/sys/block/{zram_dev}/disksize", "r") as f:
                    mem_info["zram"]["total"] = int(f.read().strip()) // (1024 * 1024)
            except Exception:
                pass
            
            # ZRAM stats
            try:
                with open(f"/sys/block/{zram_dev}/mm_stat", "r") as f:
                    stats = f.read().split()
                    if len(stats) >= 3:
                        mem_info["zram"]["used"] = int(stats[2]) // (1024 * 1024)
            except Exception:
                pass
        
        return mem_info
    
    def analyze_kernel(self) -> Dict[str, Any]:
        """Analyze kernel information."""
        kernel_info = {
            "version": "",
            "release": "",
            "arch": "",
            "selinux": "",
            "magisk": False
        }
        
        # Kernel version
        kernel_info["version"] = self.execute_command("uname -r") or ""
        kernel_info["release"] = self.execute_command("uname -v") or ""
        kernel_info["arch"] = self.execute_command("uname -m") or ""
        
        # SELinux status
        selinux = self.execute_command("getenforce")
        if selinux:
            kernel_info["selinux"] = selinux
        else:
            # Try alternative method
            try:
                with open("/sys/fs/selinux/enforce", "r") as f:
                    val = f.read().strip()
                    kernel_info["selinux"] = "Enforcing" if val == "1" else "Permissive"
            except Exception:
                kernel_info["selinux"] = "Unknown"
        
        # Magisk detection
        magisk_paths = [
            "/data/adb/magisk",
            "/sbin/.magisk",
            "/data/adb/modules"
        ]
        kernel_info["magisk"] = any(os.path.exists(p) for p in magisk_paths)
        
        if kernel_info["magisk"]:
            # Get Magisk version
            magisk_ver = self.execute_command("magisk -v")
            if magisk_ver:
                kernel_info["magisk_version"] = magisk_ver
        
        return kernel_info
    
    def analyze_temperature(self) -> Dict[str, Any]:
        """Analyze thermal sensors."""
        temp_info = {
            "cpu": 0,
            "battery": 0,
            "gpu": 0,
            "skin": 0,
            "sensors": []
        }
        
        # Read from thermal zones
        thermal_zones = list(Path("/sys/class/thermal").glob("thermal_zone*"))
        
        for zone in thermal_zones[:10]:  # Limit to first 10
            try:
                zone_name = "unknown"
                try:
                    with open(f"{zone}/type", "r") as f:
                        zone_name = f.read().strip()
                except Exception:
                    zone_name = zone.name
                
                with open(f"{zone}/temp", "r") as f:
                    temp_raw = int(f.read().strip())
                    temp_celsius = temp_raw / 1000.0
                    
                    sensor_data = {
                        "name": zone_name,
                        "temperature": temp_celsius
                    }
                    temp_info["sensors"].append(sensor_data)
                    
                    # Map to common categories
                    name_lower = zone_name.lower()
                    if "cpu" in name_lower and temp_info["cpu"] == 0:
                        temp_info["cpu"] = temp_celsius
                    elif "battery" in name_lower and temp_info["battery"] == 0:
                        temp_info["battery"] = temp_celsius
                    elif "gpu" in name_lower and temp_info["gpu"] == 0:
                        temp_info["gpu"] = temp_celsius
                    elif "skin" in name_lower and temp_info["skin"] == 0:
                        temp_info["skin"] = temp_celsius
            except Exception:
                continue
        
        # Alternative: get from dumpsys
        if temp_info["battery"] == 0:
            battery_temp = self.execute_command("dumpsys battery | grep temperature")
            if battery_temp:
                match = re.search(r"temperature:\s*(\d+)", battery_temp)
                if match:
                    temp_info["battery"] = int(match.group(1)) / 10.0
        
        return temp_info
    
    def analyze_battery(self) -> Dict[str, Any]:
        """Analyze battery status."""
        battery_info = {
            "level": 0,
            "status": "",
            "health": "",
            "voltage": 0,
            "temperature": 0,
            "charging": False
        }
        
        # Use dumpsys for battery info
        dumpsys = self.execute_command("dumpsys battery")
        if dumpsys:
            level_match = re.search(r"level:\s*(\d+)", dumpsys)
            if level_match:
                battery_info["level"] = int(level_match.group(1))
            
            status_match = re.search(r"status:\s*(\d+)", dumpsys)
            if status_match:
                status_codes = {
                    "2": "Charging",
                    "3": "Discharging",
                    "4": "Not charging",
                    "5": "Full"
                }
                battery_info["status"] = status_codes.get(status_match.group(1), "Unknown")
                battery_info["charging"] = status_match.group(1) == "2"
            
            health_match = re.search(r"health:\s*(\d+)", dumpsys)
            if health_match:
                health_codes = {
                    "1": "Unknown",
                    "2": "Good",
                    "3": "Overheat",
                    "4": "Dead",
                    "5": "Over voltage"
                }
                battery_info["health"] = health_codes.get(health_match.group(1), "Unknown")
            
            voltage_match = re.search(r"voltage:\s*(\d+)", dumpsys)
            if voltage_match:
                battery_info["voltage"] = int(voltage_match.group(1))
            
            temp_match = re.search(r"temperature:\s*(\d+)", dumpsys)
            if temp_match:
                battery_info["temperature"] = int(temp_match.group(1)) / 10.0
        
        return battery_info
    
    def analyze_storage(self) -> Dict[str, Any]:
        """Analyze storage and filesystem."""
        storage_info = {
            "internal": {"total": 0, "used": 0, "available": 0},
            "sdcard": {"total": 0, "used": 0, "available": 0, "present": False},
            "filesystem": ""
        }
        
        # df for internal storage
        df_output = self.execute_command("df -h /data")
        if df_output:
            lines = df_output.split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    storage_info["internal"]["total"] = parts[1]
                    storage_info["internal"]["used"] = parts[2]
                    storage_info["internal"]["available"] = parts[3]
                    storage_info["filesystem"] = parts[0]
        
        # Check for SD card
        sd_paths = ["/storage/sdcard1", "/mnt/media_rw/sdcard1", "/storage/external_SD"]
        for sd_path in sd_paths:
            if os.path.exists(sd_path):
                storage_info["sdcard"]["present"] = True
                df_sd = self.execute_command(f"df -h {sd_path}")
                if df_sd:
                    lines = df_sd.split("\n")
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        if len(parts) >= 4:
                            storage_info["sdcard"]["total"] = parts[1]
                            storage_info["sdcard"]["used"] = parts[2]
                            storage_info["sdcard"]["available"] = parts[3]
                break
        
        return storage_info
    
    def analyze_all(self) -> Dict[str, Any]:
        """Run complete hardware analysis."""
        self.hardware_info = {
            "timestamp": self.timestamp,
            "device": {
                "model": self.execute_command("getprop ro.product.model") or "Unknown",
                "manufacturer": self.execute_command("getprop ro.product.manufacturer") or "Unknown",
                "android_version": self.execute_command("getprop ro.build.version.release") or "Unknown",
                "sdk_version": self.execute_command("getprop ro.build.version.sdk") or "Unknown",
                "termux": os.path.exists("/data/data/com.termux")
            },
            "cpu": self.analyze_cpu(),
            "gpu": self.analyze_gpu(),
            "npu": self.analyze_npu(),
            "memory": self.analyze_memory(),
            "kernel": self.analyze_kernel(),
            "temperature": self.analyze_temperature(),
            "battery": self.analyze_battery(),
            "storage": self.analyze_storage()
        }
        
        return self.hardware_info
    
    def save_report(self, filepath: str = "/workspace/FlowCore/Logs/hardware_report.json"):
        """Save hardware report to JSON file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.hardware_info, f, indent=2)
        return filepath
    
    def print_summary(self):
        """Print human-readable summary."""
        h = self.hardware_info
        
        print("=" * 60)
        print("FLOWCORE HARDWARE ANALYSIS REPORT")
        print("=" * 60)
        print(f"Device: {h['device']['manufacturer']} {h['device']['model']}")
        print(f"Android: {h['device']['android_version']} (SDK {h['device']['sdk_version']})")
        print(f"Termux: {'Yes' if h['device']['termux'] else 'No'}")
        print("-" * 60)
        print(f"CPU: {h['cpu']['cores']} cores @ {h['cpu']['frequencies'].get('max', 'N/A')} MHz")
        print(f"CPU Model: {h['cpu']['model'] or 'N/A'}")
        print(f"Governor: {h['cpu']['governor'] or 'N/A'}")
        print(f"Scheduler: {h['cpu']['scheduler'] or 'N/A'}")
        print("-" * 60)
        print(f"GPU Vulkan: {'Yes' if h['gpu']['vulkan_support'] else 'No'}")
        print(f"GPU OpenCL: {'Yes' if h['gpu']['opencl_support'] else 'No'}")
        print("-" * 60)
        print(f"NPU Present: {'Yes' if h['npu']['present'] else 'No'}")
        if h['npu']['present']:
            print(f"NPU Vendor: {h['npu']['vendor']}")
            print(f"Hexagon DSP: {'Yes' if h['npu']['hexagon_dsp'] else 'No'}")
        print("-" * 60)
        print(f"RAM: {h['memory']['ram']['used']}MB / {h['memory']['ram']['total']}MB")
        print(f"ZRAM: {'Active' if h['memory']['zram']['active'] else 'Inactive'} ({h['memory']['zram']['total']}MB)")
        print(f"Swap: {'Active' if h['memory']['swap']['active'] else 'Inactive'} ({h['memory']['swap']['total']}MB)")
        print("-" * 60)
        print(f"Kernel: {h['kernel']['version']}")
        print(f"SELinux: {h['kernel']['selinux']}")
        print(f"Magisk: {'Yes' if h['kernel']['magisk'] else 'No'}")
        if h['kernel']['magisk']:
            print(f"Magisk Version: {h['kernel'].get('magisk_version', 'Unknown')}")
        print("-" * 60)
        print(f"CPU Temp: {h['temperature']['cpu']}°C")
        print(f"Battery Temp: {h['temperature']['battery']}°C")
        print(f"Battery Level: {h['battery']['level']}%")
        print(f"Battery Status: {h['battery']['status']}")
        print(f"Charging: {'Yes' if h['battery']['charging'] else 'No'}")
        print("-" * 60)
        print(f"Internal Storage: {h['storage']['internal']['used']} / {h['storage']['internal']['total']}")
        print(f"Filesystem: {h['storage']['filesystem']}")
        print("=" * 60)


if __name__ == "__main__":
    analyzer = HardwareAnalyzer()
    analyzer.analyze_all()
    analyzer.save_report()
    analyzer.print_summary()

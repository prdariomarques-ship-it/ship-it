#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowCore Agents v1.0
Mission 7: Local AI Agents for System Management

Agents:
- PerformanceAgent: Monitor and optimize system performance
- BatteryAgent: Battery monitoring and optimization
- ThermalAgent: Temperature monitoring and thermal management
- StorageAgent: Storage monitoring and cleanup
- SecurityAgent: Security auditing and protection
- RootAgent: Root/Magisk integration
- NetworkAgent: Network monitoring
- AutomationAgent: Rule-based automation orchestrator
"""

import os
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class AgentStatus:
    """Status of an agent."""
    name: str
    active: bool = True
    last_check: str = ""
    alerts: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all FlowCore agents."""
    
    def __init__(self, name: str, check_interval: float = 30.0):
        self.name = name
        self.check_interval = check_interval
        self.status = AgentStatus(name=name)
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    @abstractmethod
    def check(self) -> Dict[str, Any]:
        """Perform agent-specific check. Returns metrics."""
        pass
    
    @abstractmethod
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on metrics."""
        pass
    
    def start_monitoring(self):
        """Start background monitoring thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[AGENT] {self.name} started monitoring")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        print(f"[AGENT] {self.name} stopped monitoring")
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                metrics = self.check()
                self.status.metrics = metrics
                self.status.last_check = datetime.now().isoformat()
                self.status.recommendations = self.get_recommendations(metrics)
            except Exception as e:
                self.status.alerts.append(f"{self.name} error: {str(e)}")
            
            time.sleep(self.check_interval)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "name": self.status.name,
            "active": self.status.active,
            "last_check": self.status.last_check,
            "alerts": self.status.alerts[-5:],  # Last 5 alerts
            "recommendations": self.status.recommendations,
            "metrics": self.status.metrics
        }


class PerformanceAgent(BaseAgent):
    """Monitor and optimize system performance."""
    
    def __init__(self):
        super().__init__("PerformanceAgent", check_interval=10.0)
    
    def check(self) -> Dict[str, Any]:
        """Check CPU and memory performance."""
        metrics = {
            "cpu_load": 0.0,
            "ram_used_mb": 0,
            "ram_total_mb": 0,
            "ram_percent": 0.0,
            "zram_active": False,
            "processes_count": 0
        }
        
        # CPU load from /proc/loadavg
        try:
            with open("/proc/loadavg", "r") as f:
                loads = f.read().split()
                metrics["cpu_load"] = float(loads[0])
        except Exception:
            pass
        
        # Memory from /proc/meminfo
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        metrics["ram_total_mb"] = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        available = int(line.split()[1]) // 1024
                        metrics["ram_used_mb"] = metrics["ram_total_mb"] - available
                        metrics["ram_percent"] = (metrics["ram_used_mb"] / max(metrics["ram_total_mb"], 1)) * 100
        except Exception:
            pass
        
        # ZRAM check
        metrics["zram_active"] = any(Path("/sys/block").glob("zram*"))
        
        # Process count
        try:
            metrics["processes_count"] = len(list(Path("/proc").glob("[0-9]*")))
        except Exception:
            pass
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations."""
        recs = []
        
        if metrics.get("ram_percent", 0) > 80:
            recs.append("HIGH RAM usage detected. Consider closing background apps.")
        
        if metrics.get("ram_percent", 0) > 90:
            recs.append("CRITICAL RAM usage! Immediate action recommended.")
        
        if metrics.get("cpu_load", 0) > 4.0:
            recs.append("High CPU load detected. Check running processes.")
        
        if not metrics.get("zram_active"):
            recs.append("ZRAM not active. Enable for better memory management.")
        
        return recs


class BatteryAgent(BaseAgent):
    """Monitor battery status and provide optimization suggestions."""
    
    def __init__(self):
        super().__init__("BatteryAgent", check_interval=60.0)
    
    def check(self) -> Dict[str, Any]:
        """Check battery status."""
        metrics = {
            "level": 0,
            "status": "Unknown",
            "health": "Unknown",
            "voltage_mv": 0,
            "temperature_c": 0.0,
            "charging": False,
            "estimated_hours": 0.0
        }
        
        # Use dumpsys for battery info
        try:
            result = subprocess.run(
                ["dumpsys", "battery"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout
            for line in output.split("\n"):
                if "level:" in line:
                    metrics["level"] = int(line.split(":")[1].strip())
                elif "status:" in line:
                    status_code = int(line.split(":")[1].strip())
                    status_map = {
                        2: "Charging",
                        3: "Discharging",
                        4: "Not charging",
                        5: "Full"
                    }
                    metrics["status"] = status_map.get(status_code, "Unknown")
                    metrics["charging"] = status_code == 2
                elif "health:" in line:
                    health_code = int(line.split(":")[1].strip())
                    health_map = {
                        1: "Unknown",
                        2: "Good",
                        3: "Overheat",
                        4: "Dead",
                        5: "Over voltage"
                    }
                    metrics["health"] = health_map.get(health_code, "Unknown")
                elif "voltage:" in line:
                    metrics["voltage_mv"] = int(line.split(":")[1].strip())
                elif "temperature:" in line:
                    metrics["temperature_c"] = int(line.split(":")[1].strip()) / 10.0
        except Exception:
            pass
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate battery recommendations."""
        recs = []
        
        level = metrics.get("level", 100)
        health = metrics.get("health", "Good")
        temp = metrics.get("temperature_c", 30)
        
        if level < 20:
            recs.append(f"LOW BATTERY ({level}%). Enable power saving mode.")
        
        if level < 10:
            recs.append(f"CRITICAL BATTERY ({level}%). Connect charger immediately.")
        
        if health != "Good":
            recs.append(f"Battery health issue detected: {health}")
        
        if temp > 40:
            recs.append(f"High battery temperature ({temp}°C). Avoid heavy usage.")
        
        if temp > 45:
            recs.append(f"CRITICAL battery temperature ({temp}°C). Stop usage and cool down.")
        
        if not metrics.get("charging") and level < 100:
            recs.append("Consider enabling battery saver mode.")
        
        return recs


class ThermalAgent(BaseAgent):
    """Monitor thermal sensors and prevent overheating."""
    
    def __init__(self):
        super().__init__("ThermalAgent", check_interval=15.0)
    
    def check(self) -> Dict[str, Any]:
        """Check thermal sensors."""
        metrics = {
            "cpu_temp": 0.0,
            "battery_temp": 0.0,
            "skin_temp": 0.0,
            "max_temp": 0.0,
            "thermal_throttling": False,
            "sensors": []
        }
        
        # Read thermal zones
        thermal_zones = list(Path("/sys/class/thermal").glob("thermal_zone*"))
        
        for zone in thermal_zones[:10]:
            try:
                zone_name = "unknown"
                try:
                    with open(f"{zone}/type", "r") as f:
                        zone_name = f.read().strip()
                except Exception:
                    zone_name = zone.name
                
                with open(f"{zone}/temp", "r") as f:
                    temp_c = int(f.read().strip()) / 1000.0
                    
                    sensor_info = {"name": zone_name, "temp": temp_c}
                    metrics["sensors"].append(sensor_info)
                    
                    name_lower = zone_name.lower()
                    if "cpu" in name_lower:
                        metrics["cpu_temp"] = max(metrics["cpu_temp"], temp_c)
                    elif "battery" in name_lower:
                        metrics["battery_temp"] = max(metrics["battery_temp"], temp_c)
                    elif "skin" in name_lower:
                        metrics["skin_temp"] = max(metrics["skin_temp"], temp_c)
                    
                    metrics["max_temp"] = max(metrics["max_temp"], temp_c)
            except Exception:
                continue
        
        # Check for throttling
        try:
            throttle_path = "/sys/devices/system/cpu/cpufreq/policy0/thermal_throttle"
            if Path(throttle_path).exists():
                metrics["thermal_throttling"] = True
        except Exception:
            pass
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate thermal recommendations."""
        recs = []
        
        max_temp = metrics.get("max_temp", 30)
        cpu_temp = metrics.get("cpu_temp", 30)
        
        if max_temp > 45:
            recs.append(f"HIGH TEMPERATURE detected ({max_temp:.1f}°C). Reduce workload.")
        
        if max_temp > 50:
            recs.append(f"CRITICAL TEMPERATURE ({max_temp:.1f}°C). Stop intensive tasks.")
        
        if cpu_temp > 55:
            recs.append(f"CPU overheating ({cpu_temp:.1f}°C). Close demanding apps.")
        
        if metrics.get("thermal_throttling"):
            recs.append("Thermal throttling active. Device is protecting itself.")
        
        if max_temp < 20:
            recs.append("Device is cold. Optimal performance expected.")
        
        return recs


class StorageAgent(BaseAgent):
    """Monitor storage and suggest cleanup actions."""
    
    def __init__(self):
        super().__init__("StorageAgent", check_interval=300.0)  # Check every 5 min
    
    def check(self) -> Dict[str, Any]:
        """Check storage status."""
        metrics = {
            "total_gb": 0.0,
            "used_gb": 0.0,
            "available_gb": 0.0,
            "used_percent": 0.0,
            "large_files": [],
            "cache_size_mb": 0
        }
        
        # df for internal storage
        try:
            result = subprocess.run(
                ["df", "-h", "/data"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    metrics["total_gb"] = self._parse_size(parts[1])
                    metrics["used_gb"] = self._parse_size(parts[2])
                    metrics["available_gb"] = self._parse_size(parts[3])
                    metrics["used_percent"] = (metrics["used_gb"] / max(metrics["total_gb"], 0.001)) * 100
        except Exception:
            pass
        
        # Estimate cache size
        cache_paths = [
            "/data/data/com.termux/cache",
            "/sdcard/Android/data",
            "/data/local/tmp"
        ]
        
        total_cache = 0
        for cache_path in cache_paths:
            path = Path(cache_path)
            if path.exists():
                try:
                    total_cache += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                except Exception:
                    continue
        
        metrics["cache_size_mb"] = total_cache // (1024 * 1024)
        
        return metrics
    
    def _parse_size(self, size_str: str) -> float:
        """Parse df size string to GB."""
        try:
            if size_str.endswith("G"):
                return float(size_str[:-1])
            elif size_str.endswith("M"):
                return float(size_str[:-1]) / 1024
            elif size_str.endswith("K"):
                return float(size_str[:-1]) / (1024 * 1024)
            else:
                return float(size_str) / (1024 * 1024 * 1024)
        except Exception:
            return 0.0
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate storage recommendations."""
        recs = []
        
        used_percent = metrics.get("used_percent", 0)
        cache_mb = metrics.get("cache_size_mb", 0)
        
        if used_percent > 80:
            recs.append(f"Storage nearly full ({used_percent:.1f}%). Free up space.")
        
        if used_percent > 90:
            recs.append(f"CRITICAL: Storage almost full ({used_percent:.1f}%). Immediate cleanup needed.")
        
        if cache_mb > 500:
            recs.append(f"Large cache detected ({cache_mb}MB). Consider clearing.")
        
        if metrics.get("available_gb", 100) < 1:
            recs.append("Less than 1GB available. Clean up files.")
        
        return recs


class SecurityAgent(BaseAgent):
    """Security auditing and protection."""
    
    def __init__(self):
        super().__init__("SecurityAgent", check_interval=60.0)
    
    def check(self) -> Dict[str, Any]:
        """Check security status."""
        metrics = {
            "root_access": False,
            "magisk_installed": False,
            "selinux_mode": "Unknown",
            "adb_enabled": False,
            "unknown_sources": False,
            "suspicious_processes": []
        }
        
        # Root check
        metrics["root_access"] = os.geteuid() == 0
        
        # Magisk check
        magisk_paths = ["/data/adb/magisk", "/sbin/.magisk", "/data/adb/modules"]
        metrics["magisk_installed"] = any(Path(p).exists() for p in magisk_paths)
        
        # SELinux
        try:
            result = subprocess.run(["getenforce"], capture_output=True, text=True, timeout=5)
            metrics["selinux_mode"] = result.stdout.strip()
        except Exception:
            try:
                with open("/sys/fs/selinux/enforce", "r") as f:
                    val = f.read().strip()
                    metrics["selinux_mode"] = "Enforcing" if val == "1" else "Permissive"
            except Exception:
                pass
        
        # ADB check
        try:
            result = subprocess.run(
                ["getprop", "persist.service.adb.enable"],
                capture_output=True,
                text=True,
                timeout=5
            )
            metrics["adb_enabled"] = result.stdout.strip() == "1"
        except Exception:
            pass
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate security recommendations."""
        recs = []
        
        if metrics.get("selinux_mode") == "Permissive":
            recs.append("SELinux is permissive. Consider enabling enforcing mode for production.")
        
        if metrics.get("adb_enabled"):
            recs.append("ADB is enabled. Disable when not debugging.")
        
        if not metrics.get("root_access"):
            recs.append("Running without root. Some features may be limited.")
        
        if metrics.get("magisk_installed"):
            recs.append("Magisk detected. Ensure modules are from trusted sources.")
        
        return recs


class RootAgent(BaseAgent):
    """Root and Magisk integration."""
    
    def __init__(self):
        super().__init__("RootAgent", check_interval=120.0)
    
    def check(self) -> Dict[str, Any]:
        """Check root and Magisk status."""
        metrics = {
            "root": False,
            "magisk_version": "",
            "magisk_modules": [],
            "safe_mode": False,
            "zygisk_enabled": False
        }
        
        metrics["root"] = os.geteuid() == 0
        
        if metrics["root"]:
            # Get Magisk version
            try:
                result = subprocess.run(
                    ["magisk", "-v"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                metrics["magisk_version"] = result.stdout.strip()
            except Exception:
                pass
            
            # List Magisk modules
            modules_dir = Path("/data/adb/modules")
            if modules_dir.exists():
                for module in modules_dir.iterdir():
                    if module.is_dir():
                        try:
                            with open(module / "module.prop", "r") as f:
                                for line in f:
                                    if line.startswith("name="):
                                        metrics["magisk_modules"].append(line.split("=")[1].strip())
                        except Exception:
                            continue
            
            # Check Zygisk
            zygisk_lib = Path("/data/adb/zygisk")
            metrics["zygisk_enabled"] = zygisk_lib.exists()
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate root-related recommendations."""
        recs = []
        
        if not metrics.get("root"):
            recs.append("Device not rooted. Some advanced features unavailable.")
            return recs
        
        if not metrics.get("magisk_version"):
            recs.append("Rooted but Magisk not found. Consider installing Magisk for better management.")
        
        if metrics.get("magisk_modules"):
            recs.append(f"Active Magisk modules: {len(metrics['magisk_modules'])}")
        
        return recs


class NetworkAgent(BaseAgent):
    """Network monitoring."""
    
    def __init__(self):
        super().__init__("NetworkAgent", check_interval=30.0)
    
    def check(self) -> Dict[str, Any]:
        """Check network status."""
        metrics = {
            "wifi_connected": False,
            "wifi_ssid": "",
            "mobile_data": False,
            "ip_address": "",
            "dns_servers": [],
            "signal_strength": 0
        }
        
        try:
            # WiFi check
            result = subprocess.run(
                ["dumpsys", "wifi"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout
            if "mNetworkInfo" in output and "CONNECTED" in output:
                metrics["wifi_connected"] = True
            
            # SSID
            import re
            ssid_match = re.search(r'SSID: ([^,]+)', output)
            if ssid_match:
                metrics["wifi_ssid"] = ssid_match.group(1).strip('"')
            
            # Signal strength
            rssi_match = re.search(r'RSSI: (-?\d+)', output)
            if rssi_match:
                metrics["signal_strength"] = int(rssi_match.group(1))
        except Exception:
            pass
        
        # IP address
        try:
            result = subprocess.run(
                ["ip", "addr", "show", "wlan0"],
                capture_output=True,
                text=True,
                timeout=5
            )
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
            if ip_match:
                metrics["ip_address"] = ip_match.group(1)
        except Exception:
            pass
        
        return metrics
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate network recommendations."""
        recs = []
        
        signal = metrics.get("signal_strength", 0)
        
        if signal < -80:
            recs.append("Weak WiFi signal. Consider moving closer to router.")
        
        if not metrics.get("wifi_connected") and not metrics.get("mobile_data"):
            recs.append("No network connection detected.")
        
        return recs


class AutomationAgent(BaseAgent):
    """Rule-based automation orchestrator."""
    
    def __init__(self):
        super().__init__("AutomationAgent", check_interval=5.0)
        self.rules: List[Dict[str, Any]] = []
        self.actions_executed: List[Dict[str, Any]] = []
    
    def add_rule(self, rule: Dict[str, Any]):
        """Add an automation rule."""
        self.rules.append(rule)
        print(f"[AUTOMATION] Added rule: {rule.get('name', 'unnamed')}")
    
    def check(self) -> Dict[str, Any]:
        """Check all automation rules."""
        metrics = {
            "rules_count": len(self.rules),
            "active_rules": 0,
            "triggers_today": 0,
            "last_trigger": ""
        }
        
        # Count active rules
        metrics["active_rules"] = sum(1 for r in self.rules if r.get("enabled", True))
        
        return metrics
    
    def evaluate_rules(self, context: Dict[str, Any]) -> List[str]:
        """Evaluate all rules against current context."""
        triggered = []
        
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            
            # Check conditions
            conditions_met = True
            for condition in rule.get("conditions", []):
                if not self._check_condition(condition, context):
                    conditions_met = False
                    break
            
            if conditions_met:
                # Execute actions
                for action in rule.get("actions", []):
                    self._execute_action(action, rule.get("name", "unnamed"))
                    triggered.append(f"Rule '{rule.get('name')}': {action.get('type')}")
        
        return triggered
    
    def _check_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if a condition is met."""
        metric = condition.get("metric")
        operator = condition.get("operator", ">")
        threshold = condition.get("threshold")
        
        value = context.get(metric, 0)
        
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        
        return False
    
    def _execute_action(self, action: Dict[str, Any], rule_name: str):
        """Execute an automation action."""
        action_type = action.get("type")
        
        action_record = {
            "timestamp": datetime.now().isoformat(),
            "rule": rule_name,
            "action": action_type,
            "executed": False
        }
        
        # Safety check - never execute destructive actions without confirmation
        destructive_actions = ["reboot", "shutdown", "delete", "format", "wipe"]
        if any(d in action_type.lower() for d in destructive_actions):
            print(f"[AUTOMATION] BLOCKED destructive action: {action_type} from rule {rule_name}")
            action_record["blocked"] = True
            self.actions_executed.append(action_record)
            return
        
        print(f"[AUTOMATION] Executing: {action_type}")
        action_record["executed"] = True
        self.actions_executed.append(action_record)
    
    def get_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate automation recommendations."""
        recs = []
        
        if metrics.get("rules_count", 0) == 0:
            recs.append("No automation rules configured. Consider adding rules for common scenarios.")
        
        recent_actions = [a for a in self.actions_executed 
                         if datetime.fromisoformat(a["timestamp"]).hour == datetime.now().hour]
        
        if len(recent_actions) > 10:
            recs.append("High automation activity in the last hour. Review rules.")
        
        return recs


# Agent Registry
class AgentRegistry:
    """Central registry for all agents."""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self._register_default_agents()
    
    def _register_default_agents(self):
        """Register all default agents."""
        self.register(PerformanceAgent())
        self.register(BatteryAgent())
        self.register(ThermalAgent())
        self.register(StorageAgent())
        self.register(SecurityAgent())
        self.register(RootAgent())
        self.register(NetworkAgent())
        self.register(AutomationAgent())
    
    def register(self, agent: BaseAgent):
        """Register an agent."""
        self.agents[agent.name] = agent
        print(f"[REGISTRY] Registered: {agent.name}")
    
    def start_all(self):
        """Start all agents."""
        for agent in self.agents.values():
            agent.start_monitoring()
    
    def stop_all(self):
        """Stop all agents."""
        for agent in self.agents.values():
            agent.stop_monitoring()
    
    def get_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific agent."""
        if agent_name in self.agents:
            return self.agents[agent_name].get_status()
        return None
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all agents."""
        return {name: agent.get_status() for name, agent in self.agents.items()}
    
    def get_recommendations(self) -> Dict[str, List[str]]:
        """Get recommendations from all agents."""
        return {
            name: agent.status.recommendations 
            for name, agent in self.agents.items() 
            if agent.status.recommendations
        }


if __name__ == "__main__":
    # Example usage
    registry = AgentRegistry()
    
    print("\n" + "=" * 60)
    print("FLOWCORE AGENT SYSTEM")
    print("=" * 60)
    
    # Start all agents
    registry.start_all()
    
    # Wait for some checks
    time.sleep(2)
    
    # Get all status
    all_status = registry.get_all_status()
    
    for name, status in all_status.items():
        print(f"\n--- {name} ---")
        print(f"Active: {status['active']}")
        print(f"Last Check: {status['last_check']}")
        if status['recommendations']:
            print("Recommendations:")
            for rec in status['recommendations']:
                print(f"  • {rec}")
    
    # Get consolidated recommendations
    print("\n" + "=" * 60)
    print("ALL RECOMMENDATIONS")
    print("=" * 60)
    
    recs = registry.get_recommendations()
    for agent_name, agent_recs in recs.items():
        print(f"\n{agent_name}:")
        for rec in agent_recs:
            print(f"  → {rec}")
    
    # Stop all agents
    registry.stop_all()
    print("\nAll agents stopped.")

#!/usr/bin/env python3
"""
FlowCore Launcher Principal
Ponto de entrada único para o FlowCore no Android/Termux

Uso:
    python flowcore.py start      # Inicia todos os serviços
    python flowcore.py stop       # Para todos os serviços
    python flowcore.py restart    # Reinicia serviços
    python flowcore.py status     # Mostra status
    python flowcore.py health     # Health check
    python flowcore.py executor   # Inicia apenas executor
    python flowcore.py api        # Inicia apenas API
    python flowcore.py logs       # Mostra logs recentes
    python flowcore.py doctor     # Diagnóstico do sistema
    python flowcore.py benchmark  # Roda benchmarks
    python flowcore.py optimize   # Otimiza configurações
    python flowcore.py update     # Atualiza FlowCore
    python flowcore.py repair     # Repara instalação
"""

import sys
import os
import argparse
import signal
import time
from pathlib import Path
from datetime import datetime

# Configurar caminho base - Compatível com Termux
if __name__ == "__main__":
    # Obter diretório base (funciona no Termux)
    BASE_DIR = Path(__file__).parent.absolute()
    sys.path.insert(0, str(BASE_DIR))
    
    # Configurar variáveis de ambiente para Termux
    os.environ.setdefault("FLOWCORE_BASE", str(BASE_DIR))
    os.environ.setdefault("PYTHONPATH", f"{BASE_DIR}:{os.environ.get('PYTHONPATH', '')}")

from FlowCore.Executor.logger import get_logger
from FlowCore.Executor.permissions import get_permission_manager

# ==================== Configuração ====================

LOGO = r"""
  _____ _       _             _ 
 |  ___| |     | |           | |
 | |_  | | __ _| |_ ___  __ _| |
 |  _| | |/ _` | __/ _ \/ _` | |
 | |   | | (_| | ||  __/ (_| | |
 \_|   |_|\__,_|\__\___|\__,_|_|
                                
 FlowCore AI Engine v1.0
 Runtime Local para Android/Termux
"""

class FlowCoreLauncher:
    """Gerenciador principal do FlowCore"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.absolute()
        self.logger = get_logger()
        self.permission_manager = get_permission_manager()
        self.running = False
        self.processes = []
        
        # Caminhos compatíveis com Termux
        self.pid_dir = self.base_dir / "Logs" / "pids"
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        
    def setup_signal_handlers(self):
        """Configurar handlers para sinais Unix"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handler para interrupção"""
        self.logger.warning(f"Sinal recebido: {signum}. Iniciando shutdown...")
        self.stop_all()
        sys.exit(0)
        
    def check_termux_environment(self) -> bool:
        """Verificar se está rodando no Termux"""
        is_termux = "TERMUX_VERSION" in os.environ or "/data/data/com.termux" in str(Path.home())
        if is_termux:
            self.logger.info("Ambiente Termux detectado")
        else:
            self.logger.info("Ambiente não-Termux detectado (modo compatibilidade)")
        return is_termux
        
    def get_python_executable(self) -> str:
        """Obter executável Python correto para o ambiente"""
        # Prioridade: python3.13 > python3 > python
        if sys.version_info >= (3, 13):
            return "python3.13" if self._cmd_exists("python3.13") else sys.executable
        elif sys.version_info >= (3, 0):
            return "python3" if self._cmd_exists("python3") else sys.executable
        return sys.executable
        
    def _cmd_exists(self, cmd: str) -> bool:
        """Verificar se comando existe"""
        import shutil
        return shutil.which(cmd) is not None
        
    def start_executor(self, background: bool = False) -> bool:
        """Iniciar Executor Engine"""
        try:
            self.logger.info("Iniciando FlowCore Executor...")
            
            if background:
                # Executar em background
                import subprocess
                cmd = [sys.executable, str(self.base_dir / "Executor" / "scheduler.py")]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(self.base_dir)
                )
                self.processes.append(proc)
                
                # Salvar PID
                pid_file = self.pid_dir / "executor.pid"
                pid_file.write_text(str(proc.pid))
                
                self.logger.info(f"Executor iniciado em background (PID: {proc.pid})")
            else:
                # Importar e rodar diretamente
                from FlowCore.Executor.scheduler import TaskScheduler
                scheduler = TaskScheduler()
                scheduler.start()
                
            return True
        except Exception as e:
            self.logger.error(f"Falha ao iniciar executor: {e}")
            return False
            
    def start_api(self, background: bool = False) -> bool:
        """Iniciar API REST"""
        try:
            self.logger.info("Iniciando FlowCore API...")
            
            if background:
                import subprocess
                cmd = [
                    sys.executable,
                    str(self.base_dir / "API" / "api.py"),
                    "--host", "127.0.0.1",
                    "--port", "8765"
                ]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(self.base_dir)
                )
                self.processes.append(proc)
                
                # Salvar PID
                pid_file = self.pid_dir / "api.pid"
                pid_file.write_text(str(proc.pid))
                
                self.logger.info(f"API iniciada em background (PID: {proc.pid})")
            else:
                # Importar e rodar
                import uvicorn
                from FlowCore.API.api import app
                uvicorn.run(app, host="127.0.0.1", port=8765)
                
            return True
        except Exception as e:
            self.logger.error(f"Falha ao iniciar API: {e}")
            return False
            
    def start_watchdog(self) -> bool:
        """Iniciar Watchdog"""
        try:
            self.logger.info("Iniciando FlowCore Watchdog...")
            from FlowCore.Watchdog.watchdog import WatchdogService
            watchdog = WatchdogService()
            watchdog.start_background()
            return True
        except Exception as e:
            self.logger.error(f"Falha ao iniciar watchdog: {e}")
            return False
            
    def start_all(self):
        """Iniciar todos os serviços"""
        print(LOGO)
        self.logger.info("=" * 60)
        self.logger.info("INICIANDO FLOWCORE AI ENGINE")
        self.logger.info("=" * 60)
        
        self.check_termux_environment()
        self.setup_signal_handlers()
        
        # Iniciar componentes
        success = True
        success &= self.start_executor(background=True)
        time.sleep(1)
        success &= self.start_api(background=True)
        time.sleep(1)
        success &= self.start_watchdog()
        
        if success:
            self.logger.info("=" * 60)
            self.logger.info("✅ FLOWCORE INICIADO COM SUCESSO")
            self.logger.info("API: http://127.0.0.1:8765")
            self.logger.info("Logs: ~/FlowCore/Logs/")
            self.logger.info("Para parar: flowcore stop")
            self.logger.info("=" * 60)
            self.running = True
        else:
            self.logger.error("Falha ao iniciar alguns componentes")
            
    def stop_all(self):
        """Parar todos os serviços"""
        self.logger.info("Parando FlowCore...")
        
        # Ler PIDs e matar processos
        for pid_file in self.pid_dir.glob("*.pid"):
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                self.logger.info(f"Processo {pid} parado")
                pid_file.unlink()
            except (ProcessLookupError, ValueError):
                pass
                
        # Matar processos locais
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
                    
        self.logger.info("FlowCore parado")
        self.running = False
        
    def show_status(self):
        """Mostrar status dos serviços"""
        print("\n" + "=" * 60)
        print("FLOWCORE STATUS")
        print("=" * 60)
        
        services = {
            "Executor": "executor.pid",
            "API": "api.pid",
            "Watchdog": "watchdog.pid"
        }
        
        for name, pid_file in services.items():
            pid_path = self.pid_dir / pid_file
            if pid_path.exists():
                try:
                    pid = int(pid_path.read_text().strip())
                    os.kill(pid, 0)  # Verifica se processo existe
                    print(f"✓ {name}: RODANDO (PID: {pid})")
                except (ProcessLookupError, ValueError):
                    print(f"✗ {name}: PARADO (PID inválido)")
            else:
                print(f"✗ {name}: PARADO")
                
        print("=" * 60)
        
    def health_check(self) -> bool:
        """Realizar health check"""
        import urllib.request
        import json
        
        try:
            req = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5)
            data = json.loads(req.read().decode())
            
            if data.get("status") == "healthy":
                print("✓ Health Check: PASSED")
                print(f"  Status: {data.get('status')}")
                print(f"  Version: {data.get('version')}")
                print(f"  Timestamp: {data.get('timestamp')}")
                return True
            else:
                print("✗ Health Check: FAILED")
                return False
        except Exception as e:
            print(f"✗ Health Check: FAILED - {e}")
            return False
            
    def show_logs(self, lines: int = 50):
        """Mostrar logs recentes"""
        log_file = self.base_dir / "Logs" / "flowcore.log"
        
        if not log_file.exists():
            print("Nenhum log encontrado")
            return
            
        try:
            content = log_file.read_text(encoding="utf-8")
            last_lines = content.splitlines()[-lines:]
            print("\n".join(last_lines))
        except Exception as e:
            print(f"Erro ao ler logs: {e}")
            
    def run_doctor(self):
        """Diagnóstico completo do sistema"""
        from FlowCore.Scripts.hardware_analyzer import HardwareAnalyzer
        
        print(LOGO)
        print("\n" + "=" * 60)
        print("FLOWCORE DOCTOR - DIAGNÓSTICO DO SISTEMA")
        print("=" * 60 + "\n")
        
        analyzer = HardwareAnalyzer()
        report = analyzer.analyze_all()
        
        print("\n--- Resumo do Hardware ---")
        print(f"CPU: {report.get('cpu', {}).get('model', 'Desconhecido')}")
        print(f"Cores: {report.get('cpu', {}).get('cores', 'N/A')}")
        print(f"RAM Total: {report.get('memory', {}).get('total_gb', 'N/A')} GB")
        print(f"RAM Disponível: {report.get('memory', {}).get('available_gb', 'N/A')} GB")
        print(f"Storage: {report.get('storage', {}).get('free_gb', 'N/A')} GB livres")
        print(f"Python: {sys.version}")
        print(f"Termux: {'Sim' if self.check_termux_environment() else 'Não'}")
        
        # Verificar dependências
        print("\n--- Dependências ---")
        deps = ["fastapi", "uvicorn", "pydantic"]
        for dep in deps:
            try:
                __import__(dep)
                print(f"✓ {dep}")
            except ImportError:
                print(f"✗ {dep} (não instalado)")
                
        # Verificar permissões
        print("\n--- Permissões ---")
        pm = self.permission_manager
        test_cmd = "echo test"
        is_safe, msg = pm.is_command_safe(test_cmd)
        if is_safe:
            print("✓ Comandos básicos permitidos")
        else:
            print(f"✗ Restrições de comando detectadas: {msg}")
            
        print("\n" + "=" * 60)
        print("DIAGNÓSTICO CONCLUÍDO")
        print("=" * 60)
        
    def run_benchmark(self):
        """Executar benchmarks"""
        print(LOGO)
        print("\nExecutando benchmarks...")
        
        # Importar hardware analyzer para benchmark
        from FlowCore.Scripts.hardware_analyzer import HardwareAnalyzer
        
        analyzer = HardwareAnalyzer()
        results = analyzer.run_cpu_benchmark()
        
        print("\n--- CPU Benchmark ---")
        print(f"Score: {results.get('score', 'N/A')}")
        print(f"Operações/s: {results.get('ops_per_sec', 'N/A')}")
        
        # Benchmark de memória
        mem_results = analyzer.run_memory_benchmark()
        print("\n--- Memory Benchmark ---")
        print(f"Leitura: {mem_results.get('read_speed', 'N/A')} MB/s")
        print(f"Escrita: {mem_results.get('write_speed', 'N/A')} MB/s")
        
    def run_optimize(self):
        """Otimizar configurações"""
        print("Otimizando FlowCore para seu hardware...")
        
        # Aqui entrariam otimizações específicas
        config_file = self.base_dir / "Config" / "optimized.json"
        
        optimizations = {
            "max_workers": 4,
            "thread_pool_size": 8,
            "cache_size_mb": 512,
            "timeout_seconds": 300
        }
        
        import json
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(optimizations, indent=2))
        
        print("✓ Configurações otimizadas salvas em Config/optimized.json")
        
    def run_update(self):
        """Atualizar FlowCore"""
        print("Verificando atualizações...")
        print("Nota: Use 'git pull' para atualizar o repositório")
        
    def run_repair(self):
        """Reparar instalação"""
        print("Reparando instalação do FlowCore...")
        
        # Recriar diretórios necessários
        dirs = ["Logs", "Models", "Config", "Logs/pids"]
        for d in dirs:
            path = self.base_dir / d
            path.mkdir(parents=True, exist_ok=True)
            print(f"✓ Diretório {d} verificado")
            
        # Limpar cache Python
        import shutil
        for pycache in self.base_dir.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
            except:
                pass
        print("✓ Cache Python limpo")
        
        print("Reparo concluído!")


def main():
    parser = argparse.ArgumentParser(
        description="FlowCore AI Engine - Launcher Principal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python flowcore.py start      # Inicia todos os serviços
  python flowcore.py stop       # Para todos os serviços
  python flowcore.py status     # Mostra status
  python flowcore.py health     # Health check
  python flowcore.py doctor     # Diagnóstico completo
  python flowcore.py benchmark  # Roda benchmarks
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=[
            "start", "stop", "restart", "status", "health",
            "executor", "api", "logs", "doctor", "benchmark",
            "optimize", "update", "repair"
        ],
        help="Comando a executar"
    )
    
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verbose")
    parser.add_argument("--background", "-b", action="store_true", help="Executar em background")
    
    args = parser.parse_args()
    
    launcher = FlowCoreLauncher()
    
    # Mapear comandos
    commands = {
        "start": lambda: launcher.start_all(),
        "stop": lambda: launcher.stop_all(),
        "restart": lambda: [launcher.stop_all(), time.sleep(2), launcher.start_all()],
        "status": lambda: launcher.show_status(),
        "health": lambda: launcher.health_check(),
        "executor": lambda: launcher.start_executor(background=args.background),
        "api": lambda: launcher.start_api(background=args.background),
        "logs": lambda: launcher.show_logs(),
        "doctor": lambda: launcher.run_doctor(),
        "benchmark": lambda: launcher.run_benchmark(),
        "optimize": lambda: launcher.run_optimize(),
        "update": lambda: launcher.run_update(),
        "repair": lambda: launcher.run_repair()
    }
    
    if args.command in commands:
        result = commands[args.command]()
        if result is False:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

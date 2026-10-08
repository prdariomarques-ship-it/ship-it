"""
FlowCore Watchdog
Monitor e auto-reinício do Executor
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import threading

# Adicionar FlowCore ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FlowCore.Executor.logger import get_logger


class Watchdog:
    """
    Watchdog para monitorar e reiniciar o Executor automaticamente
    
    Funcionalidades:
    - Monitora processo do Executor
    - Reinicia automaticamente se cair
    - Detecta travamentos
    - Logs de eventos
    - Graceful shutdown
    """
    
    def __init__(self, 
                 executor_script: str = None,
                 max_restarts: int = 5,
                 restart_delay: int = 3,
                 health_check_interval: int = 30,
                 log_dir: str = None):
        """
        Inicializa o Watchdog
        
        Args:
            executor_script: caminho do script do executor
            max_restarts: máximo de reinícios antes de desistir
            restart_delay: delay entre reinícios (segundos)
            health_check_interval: intervalo entre checks de saúde
            log_dir: diretório para logs
        """
        self.executor_script = executor_script or str(
            Path(__file__).parent.parent / "API" / "api.py"
        )
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.health_check_interval = health_check_interval
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent / "Logs"
        
        self.logger = get_logger()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Estado
        self.process: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self.is_running = False
        self.last_health_check: Optional[datetime] = None
        self.consecutive_failures = 0
        
        # Controle
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.on_start: Optional[Callable[[], None]] = None
        self.on_stop: Optional[Callable[[], None]] = None
        self.on_restart: Optional[Callable[[int], None]] = None
        self.on_max_restarts: Optional[Callable[[], None]] = None
    
    def start(self):
        """Inicia o watchdog e o executor"""
        if self.is_running:
            self.logger.warning("Watchdog já está rodando")
            return
        
        self.logger.info("Iniciando FlowCore Watchdog")
        self.is_running = True
        self._stop_event.clear()
        
        # Configurar handlers de sinal
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Iniciar thread de monitoramento
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        # Iniciar thread de health check
        self._health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_thread.start()
        
        # Iniciar executor pela primeira vez
        self._start_executor()
        
        if self.on_start:
            self.on_start()
        
        self.logger.info("Watchdog iniciado com sucesso")
    
    def stop(self):
        """Para o watchdog e o executor"""
        self.logger.info("Parando Watchdog")
        self.is_running = False
        self._stop_event.set()
        
        # Parar processo do executor
        self._stop_executor()
        
        # Aguardar threads
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        if self._health_thread:
            self._health_thread.join(timeout=5)
        
        if self.on_stop:
            self.on_stop()
        
        self.logger.info("Watchdog parado")
    
    def _signal_handler(self, signum, frame):
        """Handler para sinais de interrupção"""
        self.logger.info(f"Sinal recebido: {signum}")
        self.stop()
    
    def _start_executor(self):
        """Inicia o processo do executor"""
        try:
            self.logger.info(f"Iniciando Executor: {self.executor_script}")
            
            # Comandos possíveis para iniciar o executor
            python_exec = sys.executable
            
            self.process = subprocess.Popen(
                [python_exec, self.executor_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            self.logger.info(f"Executor iniciado com PID {self.process.pid}")
            self.consecutive_failures = 0
            
            # Escrever PID em arquivo para referência
            pid_file = self.log_dir / "executor.pid"
            with open(pid_file, 'w') as f:
                f.write(str(self.process.pid))
            
        except Exception as e:
            self.logger.error(f"Falha ao iniciar executor: {str(e)}")
            self.process = None
    
    def _stop_executor(self):
        """Para o processo do executor"""
        if self.process:
            try:
                self.logger.info(f"Parando executor (PID {self.process.pid})")
                
                # Tentar graceful shutdown
                self.process.terminate()
                
                # Aguardar terminação
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill se não terminar
                    self.logger.warning("Executor não terminou, enviando SIGKILL")
                    self.process.kill()
                    self.process.wait(timeout=5)
                
                self.logger.info("Executor parado")
                
            except Exception as e:
                self.logger.error(f"Erro ao parar executor: {str(e)}")
            finally:
                self.process = None
                
                # Remover arquivo de PID
                pid_file = self.log_dir / "executor.pid"
                if pid_file.exists():
                    pid_file.unlink()
    
    def _monitor_loop(self):
        """Loop principal de monitoramento"""
        self.logger.info("Monitor loop iniciado")
        
        while not self._stop_event.is_set():
            try:
                # Verificar se processo existe
                if self.process:
                    poll_result = self.process.poll()
                    
                    if poll_result is not None:
                        # Processo terminou
                        self.logger.warning(
                            f"Executor terminou inesperadamente (código {poll_result})"
                        )
                        self.process = None
                        self._handle_crash()
                else:
                    # Processo não existe, tentar reiniciar
                    if self.restart_count < self.max_restarts:
                        self._handle_crash()
                
                # Aguardar antes de próximo check
                time.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Erro no monitor loop: {str(e)}")
                time.sleep(5)
        
        self.logger.info("Monitor loop encerrado")
    
    def _handle_crash(self):
        """Trata crash do executor"""
        self.restart_count += 1
        
        if self.restart_count > self.max_restarts:
            self.logger.error(
                f"Máximo de reinícios atingido ({self.max_restarts}). "
                "Não reiniciando mais."
            )
            
            if self.on_max_restarts:
                self.on_max_restarts()
            
            self.is_running = False
            return
        
        self.logger.info(
            f"Tentando reinício {self.restart_count}/{self.max_restarts} "
            f"em {self.restart_delay} segundos"
        )
        
        if self.on_restart:
            self.on_restart(self.restart_count)
        
        time.sleep(self.restart_delay)
        self._start_executor()
    
    def _health_check_loop(self):
        """Loop de verificação de saúde"""
        self.logger.info("Health check loop iniciado")
        
        while not self._stop_event.is_set():
            try:
                # Aguardar intervalo
                time.sleep(self.health_check_interval)
                
                if not self.process:
                    continue
                
                # Fazer health check via HTTP se possível
                self._perform_health_check()
                
            except Exception as e:
                self.logger.error(f"Erro no health check: {str(e)}")
        
        self.logger.info("Health check loop encerrado")
    
    def _perform_health_check(self):
        """Realiza health check do executor"""
        import urllib.request
        import json
        
        try:
            url = "http://127.0.0.1:8765/health"
            
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                if data.get("status") == "healthy":
                    self.last_health_check = datetime.now()
                    self.consecutive_failures = 0
                    self.logger.debug("Health check OK")
                else:
                    self.consecutive_failures += 1
                    self.logger.warning(f"Health check falhou: {data}")
                    
        except Exception as e:
            self.consecutive_failures += 1
            self.logger.warning(f"Health check exception: {str(e)}")
            
            # Se muitas falhas consecutivas, considerar crash
            if self.consecutive_failures >= 3:
                self.logger.error("Múltiplas falhas de health check, considerando crash")
                if self.process:
                    self.process.terminate()
                    self.process = None
    
    def get_status(self) -> dict:
        """Retorna status do watchdog"""
        return {
            "is_running": self.is_running,
            "executor_pid": self.process.pid if self.process else None,
            "restart_count": self.restart_count,
            "max_restarts": self.max_restarts,
            "consecutive_failures": self.consecutive_failures,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "monitor_thread_alive": self._monitor_thread.is_alive() if self._monitor_thread else False,
            "health_thread_alive": self._health_thread.is_alive() if self._health_thread else False,
        }
    
    def reset_restart_count(self):
        """Reseta contador de reinícios"""
        self.restart_count = 0
        self.logger.info("Contador de reinícios resetado")


def run_watchdog(**kwargs):
    """
    Função conveniente para rodar o watchdog
    
    Args:
        **kwargs: argumentos para Watchdog.__init__
    """
    watchdog = Watchdog(**kwargs)
    
    def on_start():
        print("\n" + "="*50)
        print("FlowCore Executor Engine INICIADO")
        print("="*50)
        print(f"PID: {watchdog.process.pid if watchdog.process else 'N/A'}")
        print(f"API: http://127.0.0.1:8765")
        print(f"Logs: {watchdog.log_dir}")
        print("="*50)
        print("Pressione Ctrl+C para parar\n")
    
    watchdog.on_start = on_start
    
    try:
        watchdog.start()
        
        # Manter thread principal viva
        while watchdog.is_running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nRecebido sinal de parada...")
    finally:
        watchdog.stop()
        print("FlowCore Executor Engine PARADO")


if __name__ == "__main__":
    run_watchdog()

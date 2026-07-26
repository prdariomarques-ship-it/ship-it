"""
FlowCore Logger Module
Sistema de logs centralizado para o Executor Engine
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


class FlowCoreLogger:
    """Logger centralizado do FlowCore com suporte a múltiplos handlers"""
    
    _instance: Optional['FlowCoreLogger'] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, name: str = "flowcore", log_dir: str = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.name = name
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent / "Logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Criar logger principal
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Evitar duplicação de handlers
        if not self.logger.handlers:
            # Handler para arquivo geral
            general_log = self.log_dir / "executor.log"
            file_handler = logging.FileHandler(general_log, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # Handler para erros críticos
            error_log = self.log_dir / "executor_errors.log"
            error_handler = logging.FileHandler(error_log, encoding='utf-8')
            error_handler.setLevel(logging.ERROR)
            
            # Handler para console (opcional)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            
            # Formatters
            detailed_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            simple_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            file_handler.setFormatter(detailed_formatter)
            error_handler.setFormatter(detailed_formatter)
            console_handler.setFormatter(simple_formatter)
            
            # Adicionar handlers
            self.logger.addHandler(file_handler)
            self.logger.addHandler(error_handler)
            self.logger.addHandler(console_handler)
        
        self._initialized = True
        
        # Logs estruturados JSON
        self.json_log_path = self.log_dir / "executor_events.json"
        self._ensure_json_log()
    
    def _ensure_json_log(self):
        """Garante que o arquivo JSON de logs exista"""
        if not self.json_log_path.exists():
            with open(self.json_log_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    def _log_json(self, event_type: str, data: dict):
        """Registra evento em formato JSON"""
        try:
            with open(self.json_log_path, 'r+', encoding='utf-8') as f:
                logs = json.load(f)
                
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "data": data
            }
            logs.append(log_entry)
            
            # Manter apenas últimos 10000 eventos
            if len(logs) > 10000:
                logs = logs[-10000:]
            
            with open(self.json_log_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Falha ao registrar log JSON: {e}")
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(message, extra=kwargs if kwargs else {})
        if kwargs:
            self._log_json("debug", {"message": message, **kwargs})
    
    def info(self, message: str, **kwargs):
        self.logger.info(message, extra=kwargs if kwargs else {})
        if kwargs:
            self._log_json("info", {"message": message, **kwargs})
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(message, extra=kwargs if kwargs else {})
        self._log_json("warning", {"message": message, **kwargs})
    
    def error(self, message: str, **kwargs):
        self.logger.error(message, extra=kwargs if kwargs else {})
        self._log_json("error", {"message": message, **kwargs})
    
    def critical(self, message: str, **kwargs):
        self.logger.critical(message, extra=kwargs if kwargs else {})
        self._log_json("critical", {"message": message, **kwargs})
    
    def command_executed(self, command: str, exit_code: int, 
                        execution_time: float, stdout: str = "", stderr: str = ""):
        """Log especializado para execução de comandos"""
        self._log_json("command_executed", {
            "command": command,
            "exit_code": exit_code,
            "execution_time_sec": execution_time,
            "stdout_length": len(stdout),
            "stderr_length": len(stderr),
            "success": exit_code == 0
        })
        
        if exit_code == 0:
            self.debug(f"Comando executado com sucesso: {command[:100]}...", 
                      execution_time=execution_time)
        else:
            self.warning(f"Comando falhou: {command[:100]}...", 
                        exit_code=exit_code, stderr=stderr[:200])
    
    def task_started(self, task_id: str, task_type: str, details: dict = None):
        """Log de início de tarefa"""
        self.info(f"Tarefa iniciada: {task_id}", 
                 task_id=task_id, task_type=task_type, details=details or {})
    
    def task_completed(self, task_id: str, success: bool, result: dict = None):
        """Log de conclusão de tarefa"""
        if success:
            self.info(f"Tarefa concluída: {task_id}", 
                     task_id=task_id, success=success, result=result or {})
        else:
            self.error(f"Tarefa falhou: {task_id}", 
                      task_id=task_id, success=success, result=result or {})
    
    def get_recent_logs(self, limit: int = 100) -> list:
        """Retorna logs recentes"""
        try:
            with open(self.json_log_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs[-limit:]
        except Exception:
            return []
    
    def clear_old_logs(self, days: int = 7):
        """Limpa logs antigos"""
        import time
        cutoff = time.time() - (days * 24 * 60 * 60)
        
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff:
                # Rotacionar em vez de deletar
                backup = log_file.with_suffix(f".{datetime.now().strftime('%Y%m%d')}.old")
                log_file.rename(backup)
                self.info(f"Log rotacionado: {log_file.name} -> {backup.name}")


# Singleton global
logger = FlowCoreLogger()


def get_logger() -> FlowCoreLogger:
    """Retorna instância singleton do logger"""
    return logger

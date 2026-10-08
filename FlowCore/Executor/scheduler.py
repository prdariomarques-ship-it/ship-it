"""
FlowCore Scheduler
Sistema de fila e agendamento de tarefas
"""

import threading
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import uuid

from .logger import get_logger
from .command_runner import get_command_runner, UnifiedCommandResult, CommandType


class TaskStatus(Enum):
    """Status possíveis de uma tarefa"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class Task:
    """Representa uma tarefa na fila"""
    id: str
    command: str
    command_type: CommandType
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[UnifiedCommandResult] = None
    priority: int = 0  # Maior = mais prioritário
    timeout: int = 300
    metadata: dict = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 1
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command": self.command[:200] if len(self.command) > 200 else self.command,
            "command_type": self.command_type.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "priority": self.priority,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "execution_time": self.result.execution_time if self.result else None,
            "success": self.result.success if self.result else None,
        }


class TaskScheduler:
    """Agendador de tarefas com fila de execução"""
    
    def __init__(self, max_workers: int = 1, max_queue_size: int = 1000):
        self.max_workers = max_workers  # Sempre 1 para execução sequencial
        self.max_queue_size = max_queue_size
        self.logger = get_logger()
        self.command_runner = get_command_runner()
        
        # Fila de tarefas (prioridade)
        self.task_queue = queue.PriorityQueue(maxsize=max_queue_size)
        
        # Estado das tarefas
        self.tasks: Dict[str, Task] = {}
        self.running_task: Optional[Task] = None
        
        # Controle de execução
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Estatísticas
        self.stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_timeout": 0,
        }
        
        # Callbacks
        self.on_task_complete: Optional[Callable[[Task], None]] = None
        self.on_task_fail: Optional[Callable[[Task], None]] = None
    
    def start(self):
        """Inicia o worker thread"""
        if self._worker_thread and self._worker_thread.is_alive():
            self.logger.warning("Scheduler já está rodando")
            return
        
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self.logger.info("Scheduler iniciado")
    
    def stop(self, wait: bool = True):
        """Para o scheduler"""
        self._stop_event.set()
        
        if wait and self._worker_thread:
            self._worker_thread.join(timeout=5)
        
        self.logger.info("Scheduler parado")
    
    def submit(self, command: str,
               command_type: CommandType = None,
               priority: int = 0,
               timeout: int = 300,
               metadata: dict = None) -> str:
        """
        Submete uma tarefa para execução
        
        Args:
            command: comando a executar
            command_type: tipo de comando
            priority: prioridade (maior = mais prioritário)
            timeout: timeout em segundos
            metadata: metadados adicionais
            
        Returns:
            str: ID da tarefa
        """
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        task = Task(
            id=task_id,
            command=command,
            command_type=command_type or CommandType.BASH,
            created_at=timestamp,
            priority=priority,
            timeout=timeout,
            metadata=metadata or {},
        )
        
        try:
            # Negativo para prioridade (maior prioridade = menor valor no PQ)
            self.task_queue.put((-priority, task_id))
            
            with self._lock:
                self.tasks[task_id] = task
            
            self.stats["total_submitted"] += 1
            self.logger.info(f"Tarefa submetida: {task_id}", 
                            command_type=task.command_type.value, 
                            priority=priority)
            
            return task_id
            
        except queue.Full:
            self.logger.error("Fila cheia, tarefa rejeitada")
            raise Exception("Fila de tarefas cheia")
    
    def cancel(self, task_id: str) -> bool:
        """Cancela uma tarefa pendente"""
        with self._lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now().isoformat()
                self.stats["total_cancelled"] += 1
                self.logger.info(f"Tarefa cancelada: {task_id}")
                return True
            
            if task.status == TaskStatus.RUNNING:
                # Não pode cancelar tarefa em execução
                self.logger.warning(f"Tentativa de cancelar tarefa em execução: {task_id}")
                return False
        
        return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Retorna informações de uma tarefa"""
        with self._lock:
            return self.tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Retorna status de uma tarefa"""
        task = self.get_task(task_id)
        return task.status if task else None
    
    def get_all_tasks(self, status_filter: TaskStatus = None) -> List[Task]:
        """Retorna todas as tarefas, opcionalmente filtradas por status"""
        with self._lock:
            tasks = list(self.tasks.values())
        
        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]
        
        # Ordenar por criação (mais recente primeiro)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks
    
    def get_queue_info(self) -> dict:
        """Retorna informações da fila"""
        with self._lock:
            pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
            running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
            completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            "queue_size": self.task_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "stats": self.stats.copy(),
            "is_running": self._worker_thread is not None and self._worker_thread.is_alive(),
        }
    
    def clear_completed(self, older_than_minutes: int = 60):
        """Limpa tarefas completadas antigas"""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(minutes=older_than_minutes)
        
        with self._lock:
            to_remove = []
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                    if task.completed_at:
                        completed_at = datetime.fromisoformat(task.completed_at)
                        if completed_at < cutoff:
                            to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            if to_remove:
                self.logger.info(f"Limpo {len(to_remove)} tarefas completadas")
    
    def _worker_loop(self):
        """Loop principal do worker"""
        self.logger.info("Worker loop iniciado")
        
        while not self._stop_event.is_set():
            try:
                # Aguardar tarefa (com timeout para verificar stop_event)
                try:
                    priority, task_id = self.task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Executar tarefa
                self._execute_task(task_id)
                
                # Marcar como done na fila
                self.task_queue.task_done()
                
            except Exception as e:
                self.logger.error(f"Erro no worker loop: {str(e)}")
                time.sleep(1)
        
        self.logger.info("Worker loop encerrado")
    
    def _execute_task(self, task_id: str):
        """Executa uma tarefa"""
        with self._lock:
            if task_id not in self.tasks:
                self.logger.error(f"Tarefa não encontrada: {task_id}")
                return
            
            task = self.tasks[task_id]
            
            # Verificar se foi cancelada
            if task.status == TaskStatus.CANCELLED:
                return
            
            # Marcar como running
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self.running_task = task
        
        self.logger.info(f"Executando tarefa: {task_id}", 
                        command=task.command[:100])
        
        try:
            # Executar comando
            result = self.command_runner.execute(
                command=task.command,
                command_type=task.command_type,
                timeout=task.timeout
            )
            
            # Atualizar tarefa
            with self._lock:
                task.result = result
                task.completed_at = datetime.now().isoformat()
                
                if result.success:
                    task.status = TaskStatus.COMPLETED
                    self.stats["total_completed"] += 1
                    
                    if self.on_task_complete:
                        self.on_task_complete(task)
                else:
                    # Verificar retry
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        task.status = TaskStatus.PENDING
                        self.logger.warning(f"Tarefa falhou, retry {task.retry_count}/{task.max_retries}")
                        
                        # Re-enfileirar
                        self.task_queue.put((-task.priority, task_id))
                        return
                    else:
                        task.status = TaskStatus.FAILED
                        self.stats["total_failed"] += 1
                        
                        if self.on_task_fail:
                            self.on_task_fail(task)
            
            self.logger.info(f"Tarefa concluída: {task_id}", 
                            success=result.success,
                            execution_time=result.execution_time)
                            
        except Exception as e:
            self.logger.error(f"Erro na execução da tarefa {task_id}: {str(e)}")
            
            with self._lock:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now().isoformat()
                task.result = UnifiedCommandResult(
                    success=False,
                    exit_code=-99,
                    stdout="",
                    stderr=str(e),
                    execution_time=0,
                    command_type=task.command_type.value,
                    command=task.command,
                    timestamp=datetime.now().isoformat()
                )
                self.stats["total_failed"] += 1
                
                if self.on_task_fail:
                    self.on_task_fail(task)
        
        finally:
            with self._lock:
                self.running_task = None
    
    def export_history(self, path: str = None) -> str:
        """Exporta histórico de tarefas para JSON"""
        if path is None:
            path = Path(__file__).parent.parent / "Logs" / "task_history.json"
        else:
            path = Path(path)
        
        with self._lock:
            history = [task.to_dict() for task in self.tasks.values()]
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Histórico exportado: {path}", task_count=len(history))
        return str(path)
    
    def import_history(self, path: str) -> int:
        """Importa histórico de tarefas (apenas leitura)"""
        path = Path(path)
        
        if not path.exists():
            return 0
        
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # Apenas carregar para referência, não re-executar
        self.logger.info(f"Histórico importado: {path}", task_count=len(history))
        return len(history)


# Singleton global
scheduler = TaskScheduler()


def get_scheduler() -> TaskScheduler:
    """Retorna instância singleton do scheduler"""
    return scheduler

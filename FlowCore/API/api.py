"""
FlowCore API
API REST local para o Executor Engine
Acesso permitido apenas via localhost
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uvicorn
import os
import socket
from pathlib import Path
from datetime import datetime

# Importar módulos do Executor
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from FlowCore.Executor.command_runner import get_command_runner, CommandType
from FlowCore.Executor.scheduler import get_scheduler, TaskStatus
from FlowCore.Executor.logger import get_logger
from FlowCore.Executor.permissions import get_permission_manager


# Configuração de segurança - Apenas localhost
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
API_PORT = int(os.environ.get("FLOWCORE_API_PORT", 8765))

# Segurança básica (opcional)
security = HTTPBasic()

# Criar aplicação FastAPI
app = FastAPI(
    title="FlowCore Executor API",
    description="API para execução de comandos locais no FlowCore",
    version="1.0.0",
    docs_url=None,  # Desabilitar Swagger UI em produção
    redoc_url="/docs",
)

logger = get_logger()
command_runner = get_command_runner()
scheduler = get_scheduler()
permission_manager = get_permission_manager()


# ==================== Modelos Pydantic ====================

class CommandRequest(BaseModel):
    """Requisição de execução de comando"""
    command: str = Field(..., min_length=1, max_length=10000)
    command_type: Optional[str] = Field(None, description="bash, python, node")
    timeout: int = Field(default=300, ge=1, le=3600)
    use_root: bool = Field(default=False)


class ScriptRequest(BaseModel):
    """Requisição de execução de script"""
    script_path: str
    args: Optional[List[str]] = []
    timeout: int = Field(default=300, ge=1, le=3600)


class FileOperationRequest(BaseModel):
    """Requisição de operação em arquivo"""
    operation: str = Field(..., description="read, write, append, mkdir, delete, exists")
    path: str
    content: Optional[str] = None
    mode: str = "utf-8"


class TaskSubmitRequest(BaseModel):
    """Requisição para submeter tarefa agendada"""
    command: str
    command_type: Optional[str] = None
    priority: int = Field(default=0, ge=-100, le=100)
    timeout: int = Field(default=300, ge=1, le=3600)


# ==================== Middleware de Segurança ====================

@app.middleware("http")
async def security_middleware(request, call_next):
    """Middleware para verificar origem das requisições"""
    client_host = request.client.host if request.client else "unknown"
    
    # Permitir apenas localhost
    if client_host not in ALLOWED_HOSTS:
        logger.warning(f"Tentativa de acesso de host não permitido: {client_host}")
        raise HTTPException(status_code=403, detail="Acesso permitido apenas via localhost")
    
    response = await call_next(request)
    return response


# ==================== Endpoints ====================

@app.get("/health")
async def health_check():
    """Verifica saúde da API"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "FlowCore Executor API",
        "version": "1.0.0",
    }


@app.get("/info")
async def get_info():
    """Retorna informações do sistema e ambiente"""
    return {
        "api_version": "1.0.0",
        "allowed_hosts": ALLOWED_HOSTS,
        "port": API_PORT,
        "permissions": permission_manager.get_permission_report(),
        "queue_info": scheduler.get_queue_info(),
        "python_info": command_runner.python_runner.get_python_info(),
        "node_info": command_runner.node_runner.get_node_info(),
    }


@app.post("/run")
async def run_command(request: CommandRequest):
    """
    Executa um comando imediatamente
    
    Suporta Bash, Python e Node.js
    """
    try:
        # Mapear tipo de comando
        cmd_type_map = {
            "bash": CommandType.BASH,
            "python": CommandType.PYTHON,
            "node": CommandType.NODE,
        }
        
        command_type = cmd_type_map.get(request.command_type.lower()) if request.command_type else None
        
        # Executar comando
        result = command_runner.execute(
            command=request.command,
            command_type=command_type,
            timeout=request.timeout,
            use_root=request.use_root if hasattr(request, 'use_root') else False
        )
        
        return result.to_dict()
        
    except Exception as e:
        logger.error(f"Erro ao executar comando: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bash")
async def run_bash(request: CommandRequest):
    """Executa comando Bash especificamente"""
    result = command_runner.execute(
        command=request.command,
        command_type=CommandType.BASH,
        timeout=request.timeout
    )
    return result.to_dict()


@app.post("/python")
async def run_python(request: CommandRequest):
    """Executa código Python"""
    result = command_runner.execute(
        command=request.command,
        command_type=CommandType.PYTHON,
        timeout=request.timeout
    )
    return result.to_dict()


@app.post("/node")
async def run_node(request: CommandRequest):
    """Executa código Node.js"""
    result = command_runner.execute(
        command=request.command,
        command_type=CommandType.NODE,
        timeout=request.timeout
    )
    return result.to_dict()


@app.post("/file")
async def file_operation(request: FileOperationRequest):
    """Executa operações em arquivos"""
    result = command_runner.execute_file_operation(
        operation=request.operation,
        path=request.path,
        content=request.content,
        mode=request.mode
    )
    return result.to_dict()


@app.get("/status")
async def get_status():
    """Retorna status do executor e fila"""
    return {
        "queue": scheduler.get_queue_info(),
        "is_running": scheduler._worker_thread is not None and scheduler._worker_thread.is_alive(),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/logs")
async def get_logs(limit: int = 100):
    """Retorna logs recentes"""
    return {
        "logs": logger.get_recent_logs(limit),
        "count": limit,
    }


@app.post("/task/submit")
async def submit_task(request: TaskSubmitRequest):
    """Submete uma tarefa para execução agendada"""
    try:
        cmd_type_map = {
            "bash": CommandType.BASH,
            "python": CommandType.PYTHON,
            "node": CommandType.NODE,
        }
        
        command_type = cmd_type_map.get(request.command_type.lower()) if request.command_type else None
        
        task_id = scheduler.submit(
            command=request.command,
            command_type=command_type,
            priority=request.priority,
            timeout=request.timeout
        )
        
        return {
            "task_id": task_id,
            "status": "submitted",
            "message": "Tarefa submetida com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    """Retorna informações de uma tarefa"""
    task = scheduler.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    return task.to_dict()


@app.get("/tasks")
async def get_all_tasks(status: Optional[str] = None):
    """Retorna todas as tarefas, opcionalmente filtradas por status"""
    if status:
        try:
            status_filter = TaskStatus(status)
            tasks = scheduler.get_all_tasks(status_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Status inválido: {status}")
    else:
        tasks = scheduler.get_all_tasks()
    
    return {
        "tasks": [t.to_dict() for t in tasks],
        "count": len(tasks),
    }


@app.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancela uma tarefa pendente"""
    success = scheduler.cancel(task_id)
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Não foi possível cancelar (tarefa não existe ou já em execução)"
        )
    
    return {"status": "cancelled", "task_id": task_id}


@app.get("/queue/info")
async def get_queue_info():
    """Retorna informações detalhadas da fila"""
    return scheduler.get_queue_info()


@app.post("/scheduler/start")
async def start_scheduler():
    """Inicia o scheduler"""
    scheduler.start()
    return {"status": "started"}


@app.post("/scheduler/stop")
async def stop_scheduler(wait: bool = True):
    """Para o scheduler"""
    scheduler.stop(wait=wait)
    return {"status": "stopped"}


# ==================== Execução do Servidor ====================

def run_server(host: str = "127.0.0.1", port: int = None, log_level: str = "info"):
    """
    Executa o servidor API
    
    Args:
        host: host para bind (sempre localhost por segurança)
        port: porta (default 8765)
        log_level: nível de log (debug, info, warning, error)
    """
    port = port or API_PORT
    
    # Iniciar scheduler
    scheduler.start()
    
    logger.info(f"Iniciando FlowCore API em {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=False,  # Desabilitar logs de acesso verbose
    )


if __name__ == "__main__":
    run_server()

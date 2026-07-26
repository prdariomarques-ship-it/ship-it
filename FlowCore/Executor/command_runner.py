"""
FlowCore Command Runner
Unificador de todos os executores (Bash, Python, Node.js)
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from enum import Enum
import time

from .logger import get_logger
from .permissions import get_permission_manager
from .shell import get_shell_runner, CommandResult
from .python_runner import get_python_runner, PythonResult
from .node_runner import get_node_runner, NodeResult


class CommandType(Enum):
    """Tipos de comandos suportados"""
    BASH = "bash"
    PYTHON = "python"
    NODE = "node"
    PYTHON_SCRIPT = "python_script"
    NODE_SCRIPT = "node_script"
    BASH_SCRIPT = "bash_script"


@dataclass
class UnifiedCommandResult:
    """Resultado unificado de execução de comando"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    command_type: str
    command: str
    timestamp: str
    metadata: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_sec": self.execution_time,
            "command_type": self.command_type,
            "command": self.command,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {},
        }


class CommandRunner:
    """Executor unificado para todos os tipos de comandos"""
    
    def __init__(self, default_timeout: int = 300):
        self.default_timeout = default_timeout
        self.logger = get_logger()
        self.permission_manager = get_permission_manager()
        self.shell_runner = get_shell_runner()
        self.python_runner = get_python_runner()
        self.node_runner = get_node_runner()
    
    def execute(self, command: str,
                command_type: CommandType = None,
                timeout: int = None,
                **kwargs) -> UnifiedCommandResult:
        """
        Executa um comando do tipo especificado
        
        Args:
            command: comando/código a executar
            command_type: tipo de comando (auto-detect se None)
            timeout: timeout em segundos
            **kwargs: argumentos específicos para cada tipo
            
        Returns:
            UnifiedCommandResult: resultado da execução
        """
        from datetime import datetime
        
        # Auto-detect tipo de comando
        if command_type is None:
            command_type = self._detect_command_type(command, kwargs)
        
        effective_timeout = timeout or self.default_timeout
        timestamp = datetime.now().isoformat()
        
        self.logger.info(f"Executando comando {command_type.value}", 
                        command=command[:100], timeout=effective_timeout)
        
        try:
            if command_type == CommandType.BASH:
                result = self._execute_bash(command, timeout=effective_timeout, **kwargs)
            elif command_type == CommandType.PYTHON:
                result = self._execute_python(command, timeout=effective_timeout, **kwargs)
            elif command_type == CommandType.NODE:
                result = self._execute_node(command, timeout=effective_timeout, **kwargs)
            elif command_type == CommandType.PYTHON_SCRIPT:
                result = self._execute_python_script(command, timeout=effective_timeout, **kwargs)
            elif command_type == CommandType.NODE_SCRIPT:
                result = self._execute_node_script(command, timeout=effective_timeout, **kwargs)
            elif command_type == CommandType.BASH_SCRIPT:
                result = self._execute_bash_script(command, timeout=effective_timeout, **kwargs)
            else:
                raise ValueError(f"Tipo de comando desconhecido: {command_type}")
            
            return UnifiedCommandResult(
                success=result.success,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=result.execution_time,
                command_type=command_type.value,
                command=command,
                timestamp=timestamp,
                metadata=getattr(result, 'locals_output', None)
            )
            
        except Exception as e:
            self.logger.error(f"Erro na execução do comando: {str(e)}")
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            return UnifiedCommandResult(
                success=False,
                exit_code=-99,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                command_type=command_type.value if command_type else "unknown",
                command=command,
                timestamp=timestamp
            )
    
    def _detect_command_type(self, command: str, kwargs: dict) -> CommandType:
        """Detecta automaticamente o tipo de comando"""
        # Verificar se é script
        if 'script_path' in kwargs:
            path = kwargs['script_path']
            if path.endswith('.py'):
                return CommandType.PYTHON_SCRIPT
            elif path.endswith('.js') or path.endswith('.mjs'):
                return CommandType.NODE_SCRIPT
            elif path.endswith('.sh'):
                return CommandType.BASH_SCRIPT
        
        # Verificar conteúdo do comando
        command_stripped = command.strip()
        
        # Detectar Python
        if command_stripped.startswith('print(') or \
           command_stripped.startswith('import ') or \
           command_stripped.startswith('def ') or \
           command_stripped.startswith('class ') or \
           '>>> ' in command_stripped:
            return CommandType.PYTHON
        
        # Detectar Node.js
        if command_stripped.startswith('console.log(') or \
           command_stripped.startswith('const ') or \
           command_stripped.startswith('let ') or \
           command_stripped.startswith('var ') or \
           command_stripped.startswith('async ') or \
           command_stripped.startswith('function '):
            return CommandType.NODE
        
        # Default é Bash
        return CommandType.BASH
    
    def _execute_bash(self, command: str, **kwargs) -> CommandResult:
        """Executa comando Bash"""
        return self.shell_runner.execute(command, **kwargs)
    
    def _execute_python(self, code: str, **kwargs) -> PythonResult:
        """Executa código Python"""
        return self.python_runner.execute_code(code, **kwargs)
    
    def _execute_node(self, code: str, **kwargs) -> NodeResult:
        """Executa código Node.js"""
        return self.node_runner.execute_code(code, **kwargs)
    
    def _execute_python_script(self, script_path: str, **kwargs) -> PythonResult:
        """Executa script Python"""
        return self.python_runner.execute_script(script_path, **kwargs)
    
    def _execute_node_script(self, script_path: str, **kwargs) -> NodeResult:
        """Executa script Node.js"""
        return self.node_runner.execute_script(script_path, **kwargs)
    
    def _execute_bash_script(self, script_path: str, **kwargs) -> CommandResult:
        """Executa script Bash"""
        return self.shell_runner.execute_script(script_path, **kwargs)
    
    def execute_file_operation(self, operation: str,
                               path: str,
                               content: str = None,
                               mode: str = 'utf-8') -> UnifiedCommandResult:
        """
        Executa operações de arquivo (ler, escrever, criar diretório)
        
        Args:
            operation: 'read', 'write', 'append', 'mkdir', 'delete', 'exists'
            path: caminho do arquivo/diretório
            content: conteúdo para escrita
            mode: modo de abertura (para leitura/escrita)
            
        Returns:
            UnifiedCommandResult: resultado da operação
        """
        from datetime import datetime
        
        timestamp = datetime.now().isoformat()
        start_time = time.time()
        
        # Verificar permissões
        is_allowed, reason = self.permission_manager.check_file_operation(operation, path)
        if not is_allowed:
            return UnifiedCommandResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Operação bloqueada por segurança: {reason}",
                execution_time=0,
                command_type="file_operation",
                command=f"{operation} {path}",
                timestamp=timestamp
            )
        
        path_obj = Path(path)
        
        try:
            if operation == 'read':
                if not path_obj.exists():
                    return UnifiedCommandResult(
                        success=False,
                        exit_code=-2,
                        stdout="",
                        stderr=f"Arquivo não existe: {path}",
                        execution_time=0,
                        command_type="file_operation",
                        command=f"read {path}",
                        timestamp=timestamp
                    )
                
                content = path_obj.read_text(encoding=mode)
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=content,
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"read {path}",
                    timestamp=timestamp,
                    metadata={"size": len(content), "lines": content.count('\n') + 1}
                )
            
            elif operation == 'write':
                # Criar diretórios pais se necessário
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                path_obj.write_text(content, encoding=mode)
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Escrito {len(content)} bytes em {path}",
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"write {path}",
                    timestamp=timestamp
                )
            
            elif operation == 'append':
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(path_obj, 'a', encoding=mode) as f:
                    f.write(content)
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Anexado {len(content)} bytes em {path}",
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"append {path}",
                    timestamp=timestamp
                )
            
            elif operation == 'mkdir':
                path_obj.mkdir(parents=True, exist_ok=True)
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Diretório criado: {path}",
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"mkdir {path}",
                    timestamp=timestamp
                )
            
            elif operation == 'delete':
                if path_obj.is_file():
                    path_obj.unlink()
                elif path_obj.is_dir():
                    import shutil
                    shutil.rmtree(path_obj)
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Removido: {path}",
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"delete {path}",
                    timestamp=timestamp
                )
            
            elif operation == 'exists':
                exists = path_obj.exists()
                return UnifiedCommandResult(
                    success=True,
                    exit_code=0,
                    stdout=str(exists),
                    stderr="",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"exists {path}",
                    timestamp=timestamp,
                    metadata={"exists": exists}
                )
            
            else:
                return UnifiedCommandResult(
                    success=False,
                    exit_code=-3,
                    stdout="",
                    stderr=f"Operação desconhecida: {operation}",
                    execution_time=time.time() - start_time,
                    command_type="file_operation",
                    command=f"{operation} {path}",
                    timestamp=timestamp
                )
                
        except Exception as e:
            return UnifiedCommandResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na operação: {str(e)}",
                execution_time=time.time() - start_time,
                command_type="file_operation",
                command=f"{operation} {path}",
                timestamp=timestamp
            )
    
    def monitor_process(self, pid: int) -> dict:
        """
        Monitora status de um processo
        
        Args:
            pid: ID do processo
            
        Returns:
            dict: informações do processo
        """
        import subprocess
        
        try:
            # Tentar obter informações do processo
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "pid,ppid,stat,time,comm"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    headers = lines[0].split()
                    values = lines[1].split()
                    return dict(zip(headers, values))
            
            return {"pid": pid, "status": "not_found"}
            
        except Exception as e:
            return {"pid": pid, "status": "error", "error": str(e)}


# Singleton global
command_runner = CommandRunner()


def get_command_runner() -> CommandRunner:
    """Retorna instância singleton do CommandRunner"""
    return command_runner

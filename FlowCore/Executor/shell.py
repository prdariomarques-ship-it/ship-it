"""
FlowCore Shell Runner
Executor de comandos Bash para Termux/Android
"""

import subprocess
import os
import shlex
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import time

from .logger import get_logger
from .permissions import get_permission_manager


@dataclass
class CommandResult:
    """Resultado da execução de um comando"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    command: str
    timestamp: str
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_sec": self.execution_time,
            "command": self.command,
            "timestamp": self.timestamp,
        }


class ShellRunner:
    """Executor de comandos Bash otimizado para Termux/Android"""
    
    def __init__(self, timeout: int = 300):
        self.timeout = timeout  # Timeout padrão em segundos
        self.logger = get_logger()
        self.permission_manager = get_permission_manager()
        self.env = self._build_environment()
    
    def _build_environment(self) -> dict:
        """Constrói ambiente seguro para execução"""
        env = os.environ.copy()
        
        # Adicionar PATH do Termux
        prefix = os.environ.get("PREFIX", "")
        if prefix:
            termux_bin = f"{prefix}/bin"
            if termux_bin not in env.get("PATH", ""):
                env["PATH"] = f"{termux_bin}:{env.get('PATH', '')}"
        
        # Configurar locale para UTF-8
        env["LANG"] = "C.UTF-8"
        env["LC_ALL"] = "C.UTF-8"
        
        # Definir HOME corretamente
        env["HOME"] = str(Path.home())
        
        return env
    
    def execute(self, command: str, 
                use_root: bool = False,
                cwd: str = None,
                env: dict = None,
                shell: bool = True,
                capture_output: bool = True,
                text: bool = True,
                timeout: int = None) -> CommandResult:
        """
        Executa um comando bash
        
        Args:
            command: comando a executar
            use_root: usar su para root
            cwd: diretório de trabalho
            env: variáveis de ambiente
            shell: usar shell (True para pipes, redirects)
            capture_output: capturar stdout/stderr
            text: retornar strings (não bytes)
            timeout: timeout em segundos
            
        Returns:
            CommandResult: resultado da execução
        """
        from datetime import datetime
        
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        effective_timeout = timeout or self.timeout
        
        # Verificar permissões
        is_safe, reason = self.permission_manager.is_command_safe(command)
        if not is_safe:
            self.logger.warning(f"Comando bloqueado por segurança: {command[:100]}", 
                               reason=reason)
            return CommandResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Comando bloqueado por segurança: {reason}",
                execution_time=0,
                command=command,
                timestamp=timestamp
            )
        
        # Preparar comando
        if use_root:
            if not self.permission_manager.is_root:
                return CommandResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="Root solicitado mas não disponível",
                    execution_time=0,
                    command=command,
                    timestamp=timestamp
                )
            full_command = ["su", "-c", command]
            run_shell = False
        else:
            full_command = command if shell else shlex.split(command)
            run_shell = shell
        
        # Preparar ambiente e diretório
        run_env = env or self.env
        run_cwd = cwd or os.getcwd()
        
        try:
            self.logger.debug(f"Executando comando: {command[:200]}...", 
                             use_root=use_root, cwd=run_cwd)
            
            result = subprocess.run(
                full_command,
                shell=run_shell,
                cwd=run_cwd,
                env=run_env,
                capture_output=capture_output,
                text=text,
                timeout=effective_timeout
            )
            
            execution_time = time.time() - start_time
            
            command_result = CommandResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time=execution_time,
                command=command,
                timestamp=timestamp
            )
            
            # Log da execução
            self.logger.command_executed(
                command=command,
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=command_result.stdout,
                stderr=command_result.stderr
            )
            
            return command_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Timeout após {effective_timeout}s: {command[:100]}")
            return CommandResult(
                success=False,
                exit_code=-2,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout: comando excedeu {effective_timeout} segundos",
                execution_time=execution_time,
                command=command,
                timestamp=timestamp
            )
            
        except FileNotFoundError as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Comando não encontrado: {command[:100]}")
            return CommandResult(
                success=False,
                exit_code=-3,
                stdout="",
                stderr=f"Comando não encontrado: {str(e)}",
                execution_time=execution_time,
                command=command,
                timestamp=timestamp
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Erro na execução: {str(e)}", command=command[:100])
            return CommandResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                command=command,
                timestamp=timestamp
            )
    
    def execute_script(self, script_path: str, 
                       args: List[str] = None,
                       use_root: bool = False) -> CommandResult:
        """
        Executa um script bash
        
        Args:
            script_path: caminho do script
            args: argumentos para o script
            use_root: usar root
            
        Returns:
            CommandResult: resultado da execução
        """
        script_path = Path(script_path)
        
        if not script_path.exists():
            return CommandResult(
                success=False,
                exit_code=-5,
                stdout="",
                stderr=f"Script não encontrado: {script_path}",
                execution_time=0,
                command=str(script_path),
                timestamp=""
            )
        
        if not script_path.is_file():
            return CommandResult(
                success=False,
                exit_code=-6,
                stdout="",
                stderr=f"NÃO é um arquivo: {script_path}",
                execution_time=0,
                command=str(script_path),
                timestamp=""
            )
        
        # Construir comando
        command = f"bash {script_path}"
        if args:
            command += " " + " ".join(shlex.quote(arg) for arg in args)
        
        return self.execute(command, use_root=use_root)
    
    def execute_multiple(self, commands: List[str],
                         stop_on_error: bool = True,
                         use_root: bool = False) -> List[CommandResult]:
        """
        Executa múltiplos comandos em sequência
        
        Args:
            commands: lista de comandos
            stop_on_error: parar no primeiro erro
            use_root: usar root para todos
            
        Returns:
            List[CommandResult]: resultados de cada comando
        """
        results = []
        
        for command in commands:
            result = self.execute(command, use_root=use_root)
            results.append(result)
            
            if stop_on_error and not result.success:
                self.logger.warning(f"Parando após erro em: {command[:100]}")
                break
        
        return results
    
    def check_command_exists(self, command: str) -> bool:
        """Verifica se um comando está disponível no PATH"""
        result = self.execute(f"command -v {command}")
        return result.success
    
    def get_available_commands(self) -> List[str]:
        """Retorna lista de comandos disponíveis no PATH"""
        result = self.execute("compgen -c")
        if result.success:
            return result.stdout.strip().split('\n')
        return []
    
    def create_temp_script(self, commands: str, 
                           prefix: str = "flowcore_") -> Path:
        """
        Cria um script temporário com comandos
        
        Args:
            commands: conteúdo do script
            prefix: prefixo do nome do arquivo
            
        Returns:
            Path: caminho do script criado
        """
        import tempfile
        
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=".sh")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write("#!/bin/bash\n")
                f.write(commands)
            
            os.chmod(path, 0o755)
            return Path(path)
        except Exception as e:
            os.close(fd)
            raise e
    
    def cleanup_temp_scripts(self, pattern: str = "flowcore_*.sh"):
        """Limpa scripts temporários"""
        import glob
        temp_dir = Path(os.environ.get("TMPDIR", "/tmp"))
        for script in temp_dir.glob(pattern):
            try:
                script.unlink()
                self.logger.debug(f"Script temporário removido: {script}")
            except Exception as e:
                self.logger.warning(f"Falha ao remover {script}: {e}")


# Singleton global
shell_runner = ShellRunner()


def get_shell_runner() -> ShellRunner:
    """Retorna instância singleton do ShellRunner"""
    return shell_runner

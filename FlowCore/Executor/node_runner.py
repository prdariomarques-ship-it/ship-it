"""
FlowCore Node.js Runner
Executor de scripts e código JavaScript/TypeScript
"""

import subprocess
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import time
import json
import tempfile

from .logger import get_logger
from .permissions import get_permission_manager


@dataclass
class NodeResult:
    """Resultado da execução de código Node.js"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    code: str
    timestamp: str
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_sec": self.execution_time,
            "code_length": len(self.code),
            "timestamp": self.timestamp,
        }


class NodeRunner:
    """Executor de código Node.js para Termux/Android"""
    
    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.logger = get_logger()
        self.permission_manager = get_permission_manager()
        self.node_exec = self._find_node()
        self.npm_exec = self._find_npm()
    
    def _find_node(self) -> str:
        """Encontra executável Node.js disponível"""
        candidates = [
            "node",
            "nodejs",
        ]
        
        for candidate in candidates:
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return candidate
            except Exception:
                continue
        
        return "node"  # Fallback
    
    def _find_npm(self) -> str:
        """Encontra executável npm disponível"""
        candidates = [
            "npm",
            "pnpm",
            "yarn",
        ]
        
        for candidate in candidates:
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return candidate
            except Exception:
                continue
        
        return "npm"  # Fallback
    
    def execute_code(self, code: str,
                     timeout: int = None,
                     use_esm: bool = False) -> NodeResult:
        """
        Executa código JavaScript/Node.js
        
        Args:
            code: código a executar
            timeout: timeout em segundos
            use_esm: usar módulo ES (import/export)
            
        Returns:
            NodeResult: resultado da execução
        """
        from datetime import datetime
        
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        effective_timeout = timeout or self.timeout
        
        # Criar script temporário
        fd, temp_path = tempfile.mkstemp(prefix="flowcore_js_", suffix=".mjs" if use_esm else ".js")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write("// FlowCore Node.js Execution\n")
                f.write(code)
            
            os.chmod(temp_path, 0o644)
            
            # Executar
            result = subprocess.run(
                [self.node_exec, temp_path],
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=os.getcwd(),
                env=os.environ.copy()
            )
            
            execution_time = time.time() - start_time
            
            node_result = NodeResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time=execution_time,
                code=code,
                timestamp=timestamp
            )
            
            # Log
            self.logger.command_executed(
                command=f"node (inline, {len(code)} chars)",
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=node_result.stdout,
                stderr=node_result.stderr
            )
            
            return node_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Timeout Node.js após {effective_timeout}s")
            return NodeResult(
                success=False,
                exit_code=-2,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout: código excedeu {effective_timeout} segundos",
                execution_time=execution_time,
                code=code,
                timestamp=timestamp
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Erro na execução Node.js: {str(e)}")
            return NodeResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                code=code,
                timestamp=timestamp
            )
        finally:
            # Limpar arquivo temporário
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
    
    def execute_script(self, script_path: str,
                       args: List[str] = None,
                       timeout: int = None,
                       cwd: str = None) -> NodeResult:
        """
        Executa um script Node.js
        
        Args:
            script_path: caminho do script
            args: argumentos para o script
            timeout: timeout em segundos
            cwd: diretório de trabalho
            
        Returns:
            NodeResult: resultado da execução
        """
        from datetime import datetime
        
        script_path = Path(script_path)
        timestamp = datetime.now().isoformat()
        start_time = time.time()
        effective_timeout = timeout or self.timeout
        run_cwd = cwd or os.getcwd()
        
        if not script_path.exists():
            return NodeResult(
                success=False,
                exit_code=-5,
                stdout="",
                stderr=f"Script não encontrado: {script_path}",
                execution_time=0,
                code="",
                timestamp=timestamp
            )
        
        if not script_path.is_file():
            return NodeResult(
                success=False,
                exit_code=-6,
                stdout="",
                stderr=f"NÃO é um arquivo: {script_path}",
                execution_time=0,
                code="",
                timestamp=timestamp
            )
        
        # Verificar permissões
        is_allowed, reason = self.permission_manager.is_path_allowed(str(script_path))
        if not is_allowed:
            return NodeResult(
                success=False,
                exit_code=-7,
                stdout="",
                stderr=f"Caminho não permitido: {reason}",
                execution_time=0,
                code="",
                timestamp=timestamp
            )
        
        # Construir comando
        command = [self.node_exec, str(script_path)]
        if args:
            command.extend(args)
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=run_cwd,
                env=os.environ.copy()
            )
            
            execution_time = time.time() - start_time
            
            node_result = NodeResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time=execution_time,
                code=f"script: {script_path}",
                timestamp=timestamp
            )
            
            # Log
            self.logger.command_executed(
                command=f"node {script_path}",
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=node_result.stdout,
                stderr=node_result.stderr
            )
            
            return node_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return NodeResult(
                success=False,
                exit_code=-2,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout: script excedeu {effective_timeout} segundos",
                execution_time=execution_time,
                code=f"script: {script_path}",
                timestamp=timestamp
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return NodeResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                code=f"script: {script_path}",
                timestamp=timestamp
            )
    
    def run_npm_command(self, command: str,
                        args: List[str] = None,
                        cwd: str = None,
                        timeout: int = None) -> NodeResult:
        """
        Executa um comando npm/yarn/pnpm
        
        Args:
            command: comando npm (install, run, build, etc.)
            args: argumentos adicionais
            cwd: diretório de trabalho (deve ter package.json)
            timeout: timeout em segundos
            
        Returns:
            NodeResult: resultado da execução
        """
        from datetime import datetime
        
        timestamp = datetime.now().isoformat()
        start_time = time.time()
        effective_timeout = timeout or self.timeout
        run_cwd = cwd or os.getcwd()
        
        # Verificar se existe package.json no diretório
        package_json = Path(run_cwd) / "package.json"
        if not package_json.exists():
            self.logger.warning(f"package.json não encontrado em {run_cwd}")
        
        # Construir comando
        cmd_args = [self.npm_exec, command]
        if args:
            cmd_args.extend(args)
        
        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=run_cwd,
                env=os.environ.copy()
            )
            
            execution_time = time.time() - start_time
            
            node_result = NodeResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time=execution_time,
                code=f"npm {command} {' '.join(args or [])}",
                timestamp=timestamp
            )
            
            # Log
            self.logger.command_executed(
                command=f"{self.npm_exec} {command}",
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=node_result.stdout,
                stderr=node_result.stderr
            )
            
            return node_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return NodeResult(
                success=False,
                exit_code=-2,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout: comando excedeu {effective_timeout} segundos",
                execution_time=execution_time,
                code=f"npm {command}",
                timestamp=timestamp
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return NodeResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                code=f"npm {command}",
                timestamp=timestamp
            )
    
    def install_packages(self, packages: List[str],
                         cwd: str = None,
                         dev: bool = False,
                         timeout: int = 600) -> NodeResult:
        """
        Instala pacotes npm
        
        Args:
            packages: lista de pacotes para instalar
            cwd: diretório de trabalho
            dev: instalar como devDependency
            timeout: timeout (padrão 10 minutos para instalações)
            
        Returns:
            NodeResult: resultado da instalação
        """
        args = packages
        if dev:
            args = ["--save-dev"] + args
        
        return self.run_npm_command("install", args, cwd=cwd, timeout=timeout)
    
    def get_node_info(self) -> dict:
        """Retorna informações sobre o ambiente Node.js"""
        try:
            # Versão do Node
            node_version = subprocess.run(
                [self.node_exec, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            ).stdout.strip()
            
            # Versão do npm
            npm_version = subprocess.run(
                [self.npm_exec, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            ).stdout.strip()
            
            return {
                "node_executable": self.node_exec,
                "node_version": node_version,
                "npm_executable": self.npm_exec,
                "npm_version": npm_version,
                "npm_package_manager": self.npm_exec,
            }
        except Exception as e:
            return {
                "error": str(e),
                "node_executable": self.node_exec,
                "npm_executable": self.npm_exec,
            }


# Singleton global
node_runner = NodeRunner()


def get_node_runner() -> NodeRunner:
    """Retorna instância singleton do NodeRunner"""
    return node_runner

"""
FlowCore Python Runner
Executor de scripts Python isolado e seguro
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
class PythonResult:
    """Resultado da execução de código Python"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    code: str
    timestamp: str
    locals_output: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_sec": self.execution_time,
            "code_length": len(self.code),
            "timestamp": self.timestamp,
            "has_locals": self.locals_output is not None,
        }


class PythonRunner:
    """Executor de código Python com isolamento e segurança"""
    
    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.logger = get_logger()
        self.permission_manager = get_permission_manager()
        self.python_exec = self._find_python()
        self.allowed_modules = self._get_allowed_modules()
    
    def _find_python(self) -> str:
        """Encontra executável Python disponível"""
        # Tentar Python 3.13 primeiro (específico do Termux)
        candidates = [
            sys.executable,  # Python atual
            "python3.13",
            "python3",
            "python",
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
        
        # Fallback para o Python atual
        return sys.executable
    
    def _get_allowed_modules(self) -> List[str]:
        """Lista de módulos permitidos para segurança"""
        # Módulos seguros para operação geral
        safe_modules = [
            "os", "sys", "pathlib", "json", "re", "math", "random",
            "datetime", "time", "collections", "itertools", "functools",
            "typing", "dataclasses", "enum", "abc",
            "subprocess", "shlex", "tempfile", "shutil",
            "logging", "hashlib", "base64", "uuid",
            "urllib.parse", "http.client", "socket",
            "threading", "multiprocessing", "concurrent.futures",
            "asyncio",
            "numpy", "pandas", "requests",  # Se instalados
        ]
        return safe_modules
    
    def execute_code(self, code: str,
                     globals_dict: dict = None,
                     locals_dict: dict = None,
                     timeout: int = None,
                     isolate: bool = True) -> PythonResult:
        """
        Executa código Python diretamente
        
        Args:
            code: código Python a executar
            globals_dict: variáveis globais
            locals_dict: variáveis locais
            timeout: timeout em segundos
            isolate: executar em processo isolado
            
        Returns:
            PythonResult: resultado da execução
        """
        from datetime import datetime
        
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        effective_timeout = timeout or self.timeout
        
        if isolate:
            return self._execute_isolated(code, timeout=effective_timeout)
        else:
            return self._execute_inline(code, globals_dict, locals_dict, 
                                       timeout=effective_timeout)
    
    def _execute_isolated(self, code: str, timeout: int) -> PythonResult:
        """Executa código em processo separado (mais seguro)"""
        from datetime import datetime
        
        start_time = time.time()
        timestamp = datetime.now().isoformat()
        
        # Criar script temporário
        fd, temp_path = tempfile.mkstemp(prefix="flowcore_py_", suffix=".py")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write("# FlowCore Python Execution\n")
                f.write("import sys\n")
                f.write("import json\n")
                f.write("\n")
                f.write(code)
                f.write("\n\n")
                f.write("# Capturar variáveis locais\n")
                f.write("_flowcore_locals = {k: v for k, v in locals().items() \n")
                f.write("                   if not k.startswith('_') and isinstance(v, (str, int, float, bool, list, dict, tuple))}\n")
                f.write("with open('/tmp/flowcore_locals.json', 'w') as f:\n")
                f.write("    json.dump(_flowcore_locals, f, default=str)\n")
            
            os.chmod(temp_path, 0o644)
            
            # Executar
            result = subprocess.run(
                [self.python_exec, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
                env=os.environ.copy()
            )
            
            execution_time = time.time() - start_time
            
            # Tentar ler variáveis locais
            locals_output = None
            try:
                locals_path = Path("/tmp/flowcore_locals.json")
                if locals_path.exists():
                    with open(locals_path, 'r') as f:
                        locals_output = json.load(f)
                    locals_path.unlink()
            except Exception:
                pass
            
            python_result = PythonResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                execution_time=execution_time,
                code=code,
                timestamp=timestamp,
                locals_output=locals_output
            )
            
            # Log
            self.logger.command_executed(
                command=f"python (isolated, {len(code)} chars)",
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=python_result.stdout,
                stderr=python_result.stderr
            )
            
            return python_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Timeout Python após {timeout}s")
            return PythonResult(
                success=False,
                exit_code=-2,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout: código excedeu {timeout} segundos",
                execution_time=execution_time,
                code=code,
                timestamp=timestamp
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Erro na execução Python: {str(e)}")
            return PythonResult(
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
    
    def _execute_inline(self, code: str, 
                       globals_dict: dict,
                       locals_dict: dict,
                       timeout: int) -> PythonResult:
        """Executa código inline (menos seguro, mais rápido)"""
        timestamp = datetime.now().isoformat()
        start_time = time.time()
        
        # Importar datetime aqui para evitar erro se não estiver no globals
        from datetime import datetime
        
        if globals_dict is None:
            globals_dict = {"__builtins__": __builtins__}
        if locals_dict is None:
            locals_dict = {}
        
        # Capturar stdout/stderr
        import io
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        
        try:
            sys.stdout = captured_stdout
            sys.stderr = captured_stderr
            
            exec(code, globals_dict, locals_dict)
            
            execution_time = time.time() - start_time
            
            stdout_value = captured_stdout.getvalue()
            stderr_value = captured_stderr.getvalue()
            
            python_result = PythonResult(
                success=True,
                exit_code=0,
                stdout=stdout_value,
                stderr=stderr_value,
                execution_time=execution_time,
                code=code,
                timestamp=timestamp,
                locals_output=locals_dict.copy()
            )
            
            return python_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            stderr_value = captured_stderr.getvalue() + f"\nError: {str(e)}"
            
            return PythonResult(
                success=False,
                exit_code=-1,
                stdout=captured_stdout.getvalue(),
                stderr=stderr_value,
                execution_time=execution_time,
                code=code,
                timestamp=timestamp
            )
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def execute_script(self, script_path: str,
                       args: List[str] = None,
                       timeout: int = None) -> PythonResult:
        """
        Executa um script Python
        
        Args:
            script_path: caminho do script
            args: argumentos para o script
            timeout: timeout em segundos
            
        Returns:
            PythonResult: resultado da execução
        """
        from datetime import datetime
        
        script_path = Path(script_path)
        timestamp = datetime.now().isoformat()
        start_time = time.time()
        effective_timeout = timeout or self.timeout
        
        if not script_path.exists():
            return PythonResult(
                success=False,
                exit_code=-5,
                stdout="",
                stderr=f"Script não encontrado: {script_path}",
                execution_time=0,
                code="",
                timestamp=timestamp
            )
        
        if not script_path.is_file():
            return PythonResult(
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
            return PythonResult(
                success=False,
                exit_code=-7,
                stdout="",
                stderr=f"Caminho não permitido: {reason}",
                execution_time=0,
                code="",
                timestamp=timestamp
            )
        
        # Construir comando
        command = [self.python_exec, str(script_path)]
        if args:
            command.extend(args)
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=script_path.parent,
                env=os.environ.copy()
            )
            
            execution_time = time.time() - start_time
            
            python_result = PythonResult(
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
                command=f"python {script_path}",
                exit_code=result.returncode,
                execution_time=execution_time,
                stdout=python_result.stdout,
                stderr=python_result.stderr
            )
            
            return python_result
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return PythonResult(
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
            return PythonResult(
                success=False,
                exit_code=-4,
                stdout="",
                stderr=f"Erro na execução: {str(e)}",
                execution_time=execution_time,
                code=f"script: {script_path}",
                timestamp=timestamp
            )
    
    def evaluate_expression(self, expression: str,
                           context: dict = None) -> Tuple[bool, Any]:
        """
        Avalia uma expressão Python e retorna o resultado
        
        Args:
            expression: expressão a avaliar
            context: contexto de variáveis
            
        Returns:
            Tuple[bool, Any]: (sucesso, resultado ou erro)
        """
        try:
            if context is None:
                context = {}
            
            result = eval(expression, {"__builtins__": __builtins__}, context)
            return True, result
        except Exception as e:
            return False, str(e)
    
    def get_python_info(self) -> dict:
        """Retorna informações sobre o ambiente Python"""
        import sys
        
        return {
            "executable": sys.executable,
            "version": sys.version,
            "version_info": list(sys.version_info),
            "path": sys.path,
            "modules_installed": len(sys.modules),
            "platform": sys.platform,
            "prefix": sys.prefix,
            "base_prefix": getattr(sys, 'base_prefix', sys.prefix),
        }


# Singleton global
python_runner = PythonRunner()


def get_python_runner() -> PythonRunner:
    """Retorna instância singleton do PythonRunner"""
    return python_runner

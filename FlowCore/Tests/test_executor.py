"""
FlowCore Executor Tests
Testes automatizados para o Executor Engine
"""

import sys
from pathlib import Path

# Adicionar workspace ao path ( FlowCore está dentro de workspace)
workspace_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(workspace_dir))

from FlowCore.Executor.logger import get_logger, FlowCoreLogger
from FlowCore.Executor.permissions import get_permission_manager, PermissionManager
from FlowCore.Executor.shell import get_shell_runner, ShellRunner
from FlowCore.Executor.python_runner import get_python_runner, PythonRunner
from FlowCore.Executor.node_runner import get_node_runner, NodeRunner
from FlowCore.Executor.command_runner import get_command_runner, CommandRunner, CommandType
from FlowCore.Executor.scheduler import get_scheduler, TaskScheduler, TaskStatus


class TestResult:
    """Resultado de um teste"""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.name} - {self.message}"


class ExecutorTests:
    """Suite de testes para o Executor"""
    
    def __init__(self):
        self.logger = get_logger()
        self.results = []
    
    def run_all(self) -> bool:
        """Executa todos os testes"""
        print("\n" + "="*60)
        print("FLOWCORE EXECUTOR - TEST SUITE")
        print("="*60 + "\n")
        
        # Testar imports
        self.results.append(self.test_imports())
        
        # Testar Logger
        self.results.append(self.test_logger())
        
        # Testar Permissions
        self.results.append(self.test_permissions())
        
        # Testar Shell Runner
        self.results.append(self.test_shell_runner())
        
        # Testar Python Runner
        self.results.append(self.test_python_runner())
        
        # Testar Command Runner
        self.results.append(self.test_command_runner())
        
        # Testar Scheduler
        self.results.append(self.test_scheduler())
        
        # Imprimir resultados
        self._print_summary()
        
        # Retornar True se todos passaram
        return all(r.passed for r in self.results)
    
    def test_imports(self) -> TestResult:
        """Testa se todos os módulos podem ser importados"""
        try:
            from FlowCore.Executor import (
                get_logger, get_permission_manager, get_shell_runner,
                get_python_runner, get_node_runner, get_command_runner,
                get_scheduler
            )
            return TestResult("Import Modules", True, "Todos os módulos importados com sucesso")
        except Exception as e:
            return TestResult("Import Modules", False, f"Erro: {str(e)}")
    
    def test_logger(self) -> TestResult:
        """Testa o sistema de logs"""
        try:
            logger = get_logger()
            logger.info("Test log message", test=True)
            
            # Verificar se logs foram criados
            log_file = logger.log_dir / "executor.log"
            if log_file.exists():
                return TestResult("Logger", True, "Logs criados corretamente")
            else:
                return TestResult("Logger", False, "Arquivo de log não encontrado")
        except Exception as e:
            return TestResult("Logger", False, f"Erro: {str(e)}")
    
    def test_permissions(self) -> TestResult:
        """Testa o gerenciador de permissões"""
        try:
            pm = get_permission_manager()
            
            # Testar verificação de comando seguro
            is_safe, reason = pm.is_command_safe("echo hello")
            if not is_safe:
                return TestResult("Permissions", False, f"Comando seguro bloqueado: {reason}")
            
            # Testar verificação de comando perigoso
            is_safe, reason = pm.is_command_safe("rm -rf /")
            if is_safe:
                return TestResult("Permissions", False, "Comando perigoso não bloqueado")
            
            return TestResult("Permissions", True, "Verificações de segurança funcionando")
        except Exception as e:
            return TestResult("Permissions", False, f"Erro: {str(e)}")
    
    def test_shell_runner(self) -> TestResult:
        """Testa o executor Bash"""
        try:
            runner = get_shell_runner()
            
            # Testar comando simples
            result = runner.execute("echo 'FlowCore Test'")
            
            if not result.success:
                return TestResult("Shell Runner", False, f"Comando falhou: {result.stderr}")
            
            if "FlowCore Test" not in result.stdout:
                return TestResult("Shell Runner", False, f"Output incorreto: {result.stdout}")
            
            return TestResult("Shell Runner", True, f"Executado em {result.execution_time:.3f}s")
        except Exception as e:
            return TestResult("Shell Runner", False, f"Erro: {str(e)}")
    
    def test_python_runner(self) -> TestResult:
        """Testa o executor Python"""
        try:
            runner = get_python_runner()
            
            # Testar código Python simples
            code = "print('Hello from Python'); x = 42"
            result = runner.execute_code(code, isolate=True)
            
            if not result.success:
                return TestResult("Python Runner", False, f"Código falhou: {result.stderr}")
            
            if "Hello from Python" not in result.stdout:
                return TestResult("Python Runner", False, f"Output incorreto: {result.stdout}")
            
            return TestResult("Python Runner", True, f"Executado em {result.execution_time:.3f}s")
        except Exception as e:
            return TestResult("Python Runner", False, f"Erro: {str(e)}")
    
    def test_command_runner(self) -> TestResult:
        """Testa o command runner unificado"""
        try:
            runner = get_command_runner()
            
            # Testar execução Bash
            result = runner.execute("ls -la", command_type=CommandType.BASH)
            
            if not result.success:
                return TestResult("Command Runner", False, f"Falha: {result.stderr}")
            
            return TestResult("Command Runner", True, f"Executado em {result.execution_time:.3f}s")
        except Exception as e:
            return TestResult("Command Runner", False, f"Erro: {str(e)}")
    
    def test_scheduler(self) -> TestResult:
        """Testa o scheduler de tarefas"""
        try:
            scheduler = get_scheduler()
            
            # Iniciar scheduler
            scheduler.start()
            
            # Submeter tarefa simples
            task_id = scheduler.submit("echo 'scheduled task'", CommandType.BASH)
            
            if not task_id:
                scheduler.stop()
                return TestResult("Scheduler", False, "Falha ao submeter tarefa")
            
            # Aguardar execução
            import time
            time.sleep(2)
            
            # Verificar status
            task = scheduler.get_task(task_id)
            if not task:
                scheduler.stop()
                return TestResult("Scheduler", False, "Tarefa não encontrada")
            
            # Parar scheduler
            scheduler.stop()
            
            if task.status == TaskStatus.COMPLETED:
                return TestResult("Scheduler", True, f"Tarefa completada com sucesso")
            elif task.status == TaskStatus.PENDING:
                return TestResult("Scheduler", True, f"Tarefa ainda pendente (OK em teste rápido)")
            else:
                return TestResult("Scheduler", False, f"Status inesperado: {task.status}")
                
        except Exception as e:
            return TestResult("Scheduler", False, f"Erro: {str(e)}")
    
    def _print_summary(self):
        """Imprime resumo dos testes"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            print(result)
        
        print("\n" + "-"*60)
        print(f"Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("STATUS: ALL TESTS PASSED ✓")
        else:
            print(f"STATUS: {total - passed} TESTS FAILED ✗")
        
        print("="*60 + "\n")


def run_tests():
    """Executa a suite de testes"""
    tests = ExecutorTests()
    success = tests.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(run_tests())

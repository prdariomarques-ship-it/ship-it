"""
FlowCore Executor Module
Módulo principal do Executor Engine
"""

from .logger import get_logger, FlowCoreLogger
from .permissions import get_permission_manager, PermissionManager
from .shell import get_shell_runner, ShellRunner, CommandResult
from .python_runner import get_python_runner, PythonRunner, PythonResult
from .node_runner import get_node_runner, NodeRunner, NodeResult
from .command_runner import get_command_runner, CommandRunner, UnifiedCommandResult, CommandType
from .scheduler import get_scheduler, TaskScheduler, Task, TaskStatus

__all__ = [
    # Logger
    'get_logger',
    'FlowCoreLogger',
    
    # Permissions
    'get_permission_manager',
    'PermissionManager',
    
    # Shell
    'get_shell_runner',
    'ShellRunner',
    'CommandResult',
    
    # Python
    'get_python_runner',
    'PythonRunner',
    'PythonResult',
    
    # Node.js
    'get_node_runner',
    'NodeRunner',
    'NodeResult',
    
    # Command Runner (unificado)
    'get_command_runner',
    'CommandRunner',
    'UnifiedCommandResult',
    'CommandType',
    
    # Scheduler
    'get_scheduler',
    'TaskScheduler',
    'Task',
    'TaskStatus',
]

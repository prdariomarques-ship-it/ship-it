"""
FlowCore Permissions Module
Gerenciamento seguro de permissões para Android/Termux
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List
import json


class PermissionManager:
    """Gerenciador de permissões para Termux/Android"""
    
    # Lista negra de comandos perigosos que nunca devem ser executados automaticamente
    DANGEROUS_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero",
        "mkfs",
        "fdisk",
        "parted",
        "echo > /dev/",
        "cat /dev/",
        ":(){:|:&};:",  # Fork bomb
        "chmod -R 777 /",
        "chown -R root:root /",
        "reboot",
        "poweroff",
        "shutdown",
        "wipe data",
        "factory_reset",
    ]
    
    # Diretórios críticos do sistema
    CRITICAL_PATHS = [
        "/system",
        "/vendor",
        "/odm",
        "/product",
        "/boot",
        "/recovery",
        "/data/data/com.android",
        "/data/system",
    ]
    
    def __init__(self):
        self.termux_prefix = os.environ.get("PREFIX", "")
        self.is_root = self._check_root()
        self.allowed_paths = self._get_allowed_paths()
    
    def _check_root(self) -> bool:
        """Verifica se tem acesso root"""
        try:
            result = subprocess.run(
                ["su", "-c", "id"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and "uid=0" in result.stdout
        except Exception:
            return False
    
    def _get_allowed_paths(self) -> List[str]:
        """Retorna lista de caminhos permitidos para operação"""
        allowed = [
            str(Path.home()),
            self.termux_prefix,
            "/sdcard",
            "/storage/emulated/0",
            os.environ.get("TMPDIR", "/tmp"),
            os.path.dirname(os.path.abspath(__file__)),
        ]
        return [p for p in allowed if p]
    
    def is_command_safe(self, command: str) -> Tuple[bool, str]:
        """
        Verifica se um comando é seguro para execução
        
        Returns:
            Tuple[bool, str]: (é_seguro, motivo)
        """
        command_lower = command.lower().strip()
        
        # Verificar lista negra
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command_lower:
                return False, f"Comando contém instrução perigosa: {dangerous}"
        
        # Verificar caminhos críticos
        for critical in self.CRITICAL_PATHS:
            if critical in command:
                return False, f"Comando acessa caminho crítico: {critical}"
        
        # Verificar se tenta modificar partições do sistema
        system_modifiers = ["mount -o rw", "remount", "systemrw"]
        for modifier in system_modifiers:
            if modifier in command_lower:
                return False, f"Comando tenta modificar partição do sistema: {modifier}"
        
        return True, "Comando parece seguro"
    
    def is_path_allowed(self, path: str) -> Tuple[bool, str]:
        """
        Verifica se um caminho está na lista de permitidos
        
        Returns:
            Tuple[bool, str]: (é_permitido, motivo)
        """
        path_obj = Path(path).resolve()
        path_str = str(path_obj)
        
        # Verificar se está em caminhos críticos
        for critical in self.CRITICAL_PATHS:
            if path_str.startswith(critical):
                return False, f"Caminho em área crítica: {critical}"
        
        # Verificar se está em caminhos permitidos
        for allowed in self.allowed_paths:
            if allowed and path_str.startswith(allowed):
                return True, f"Caminho permitido: {allowed}"
        
        # Permitir caminhos relativos dentro do diretório atual
        if not path_str.startswith("/"):
            return True, "Caminho relativo permitido"
        
        return False, f"Caminho não está na lista de permitidos: {path_str}"
    
    def check_file_operation(self, operation: str, path: str) -> Tuple[bool, str]:
        """
        Verifica se uma operação de arquivo é segura
        
        Args:
            operation: 'read', 'write', 'delete', 'execute'
            path: caminho do arquivo
            
        Returns:
            Tuple[bool, str]: (é_seguro, motivo)
        """
        # Sempre permitir leitura em maioria dos casos
        if operation == "read":
            is_allowed, reason = self.is_path_allowed(path)
            if not is_allowed:
                # Permitir leitura mesmo em alguns caminhos restritos
                for critical in self.CRITICAL_PATHS:
                    if path.startswith(critical):
                        return False, f"Leitura bloqueada em caminho crítico: {critical}"
                return True, "Leitura permitida com cautela"
            return True, reason
        
        # Escrita e deleção requerem verificação estrita
        if operation in ["write", "delete"]:
            return self.is_path_allowed(path)
        
        # Execução requer verificação adicional
        if operation == "execute":
            is_allowed, reason = self.is_path_allowed(path)
            if not is_allowed:
                return False, reason
            
            # Verificar se o arquivo existe e é executável
            path_obj = Path(path)
            if not path_obj.exists():
                return False, f"Arquivo não existe: {path}"
            
            return True, reason
        
        return False, f"Operação desconhecida: {operation}"
    
    def require_root(self, command: str) -> bool:
        """
        Verifica se um comando requer root
        
        Returns:
            bool: True se requer root
        """
        root_indicators = [
            "/system/", "/vendor/", "/data/data/",
            "pm grant", "pm revoke", "settings put global",
            "setprop", "getprop",
            "ip tables", "netfilter",
        ]
        
        command_lower = command.lower()
        return any(indicator in command_lower for indicator in root_indicators)
    
    def execute_with_permissions(self, command: str, 
                                  use_root: bool = False,
                                  allow_dangerous: bool = False) -> Tuple[bool, str, subprocess.CompletedProcess]:
        """
        Executa comando com verificação de permissões
        
        Args:
            command: comando a executar
            use_root: tentar usar root
            allow_dangerous: permitir comandos perigosos (NÃO RECOMENDADO)
            
        Returns:
            Tuple[bool, str, CompletedProcess]: (sucesso, mensagem, resultado)
        """
        # Verificar segurança
        if not allow_dangerous:
            is_safe, reason = self.is_command_safe(command)
            if not is_safe:
                return False, f"Comando bloqueado por segurança: {reason}", None
        
        # Verificar necessidade de root
        needs_root = self.require_root(command)
        if needs_root and not use_root:
            return False, "Comando requer root. Use use_root=True.", None
        
        if use_root and not self.is_root:
            return False, "Root solicitado mas não disponível", None
        
        # Construir comando final
        if use_root and self.is_root:
            full_command = ["su", "-c", command]
        else:
            full_command = command
        
        try:
            if isinstance(full_command, list):
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutos timeout
                )
            else:
                result = subprocess.run(
                    full_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            
            success = result.returncode == 0
            message = "Sucesso" if success else f"Falha: {result.stderr[:200]}"
            return success, message, result
            
        except subprocess.TimeoutExpired:
            return False, "Timeout: comando excedeu 5 minutos", None
        except Exception as e:
            return False, f"Erro na execução: {str(e)}", None
    
    def get_permission_report(self) -> dict:
        """Gera relatório de permissões atuais"""
        return {
            "is_root": self.is_root,
            "termux_prefix": self.termux_prefix,
            "allowed_paths": self.allowed_paths,
            "python_version": sys.version,
            "user_id": os.getuid(),
            "group_id": os.getgid(),
            "home_directory": str(Path.home()),
            "current_directory": os.getcwd(),
        }
    
    def audit_command_history(self, log_path: str = None) -> List[dict]:
        """
        Auditoria de comandos executados (se houver log)
        
        Returns:
            List[dict]: lista de comandos auditados
        """
        if not log_path:
            log_path = Path(__file__).parent.parent / "Logs" / "executor_events.json"
        
        if not Path(log_path).exists():
            return []
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                events = json.load(f)
            
            commands = []
            for event in events:
                if event.get("event_type") == "command_executed":
                    data = event.get("data", {})
                    commands.append({
                        "timestamp": event.get("timestamp"),
                        "command": data.get("command"),
                        "exit_code": data.get("exit_code"),
                        "success": data.get("success"),
                        "execution_time": data.get("execution_time_sec"),
                    })
            
            return commands[-100:]  # Últimos 100 comandos
        except Exception:
            return []


# Singleton global
permission_manager = PermissionManager()


def get_permission_manager() -> PermissionManager:
    """Retorna instância singleton do gerenciador de permissões"""
    return permission_manager

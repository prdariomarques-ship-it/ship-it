#!/bin/bash
# FlowCore Installation Script for Android/Termux
# Executar: bash install.sh

set -e

echo "=============================================="
echo "  FlowCore AI Engine - Instalação"
echo "  Android 15 / Termux / Python 3.13"
echo "=============================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções de log
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar se está no Termux
check_termux() {
    if [ -n "$TERMUX_VERSION" ] || [[ "$HOME" == *"/data/data/com.termux"* ]]; then
        log_info "Ambiente Termux detectado"
        return 0
    else
        log_warn "Ambiente não-Termux detectado. Alguns recursos podem não funcionar."
        return 1
    fi
}

# Verificar Python
check_python() {
    if command -v python3.13 &> /dev/null; then
        PYTHON_CMD="python3.13"
        log_info "Python 3.13 encontrado"
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        log_info "Python 3 encontrado"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
        log_info "Python encontrado"
    else
        log_error "Python não encontrado. Instale Python 3.13 no Termux:"
        echo "  pkg install python"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
    log_info "Versão: $PYTHON_VERSION"
}

# Instalar dependências do sistema
install_system_deps() {
    log_info "Verificando dependências do sistema..."
    
    if check_termux; then
        # Termux: usar pkg
        log_info "Instalando pacotes Termux..."
        
        # Verificar se pkg está disponível
        if command -v pkg &> /dev/null; then
            pkg update -y || true
            pkg install -y \
                python \
                python-pip \
                nodejs \
                git \
                wget \
                curl \
                openssl-tool \
                libjpeg-turbo \
                libpng \
                zlib \
                bzip2 \
                xz-utils \
                file \
                ncurses-utils \
                termux-exec \
                termux-api || true
            
            log_info "Pacotes Termux instalados/atualizados"
        else
            log_warn "pkg não disponível. Instalando manualmente..."
        fi
    else
        log_info "Ambiente não-Termux. Pulando instalação de pacotes do sistema."
    fi
}

# Instalar dependências Python
install_python_deps() {
    log_info "Instalando dependências Python..."
    
    # Criar requirements.txt se não existir
    if [ ! -f "requirements.txt" ]; then
        cat > requirements.txt << 'EOF'
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
httpx>=0.26.0
aiofiles>=23.2.1
psutil>=5.9.0
rich>=13.7.0
click>=8.1.7
EOF
        log_info "requirements.txt criado"
    fi
    
    # Instalar dependências
    $PYTHON_CMD -m pip install --upgrade pip --quiet
    $PYTHON_CMD -m pip install -r requirements.txt --quiet
    
    log_info "Dependências Python instaladas"
}

# Configurar ambiente
setup_environment() {
    log_info "Configurando ambiente..."
    
    # Obter diretório base
    BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
    
    # Criar diretórios necessários
    mkdir -p "$BASE_DIR/Logs"
    mkdir -p "$BASE_DIR/Logs/pids"
    mkdir -p "$BASE_DIR/Models"
    mkdir -p "$BASE_DIR/Config"
    mkdir -p "$BASE_DIR/Services"
    
    log_info "Diretórios criados"
    
    # Configurar variáveis de ambiente no .bashrc ou .zshrc
    SHELL_RC=""
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    fi
    
    if [ -n "$SHELL_RC" ]; then
        # Adicionar aliases se não existirem
        if ! grep -q "alias flowcore" "$SHELL_RC" 2>/dev/null; then
            cat >> "$SHELL_RC" << EOF

# FlowCore Aliases
alias flowcore='$PYTHON_CMD $BASE_DIR/flowcore.py'
alias fc='flowcore'
alias fc-status='flowcore status'
alias fc-start='flowcore start'
alias fc-stop='flowcore stop'
alias fc-doctor='flowcore doctor'
EOF
            log_info "Aliases adicionados ao $SHELL_RC"
            log_info "Execute 'source $SHELL_RC' para ativar"
        else
            log_info "Aliases já existem"
        fi
    fi
    
    # Exportar variáveis para sessão atual
    export FLOWCORE_BASE="$BASE_DIR"
    export PYTHONPATH="$BASE_DIR:$PYTHONPATH"
    
    log_info "Variáveis de ambiente configuradas"
}

# Criar launcher executável
create_launcher() {
    log_info "Criando launcher executável..."
    
    LAUNCHER_BIN="$BASE_DIR/flowcore"
    
    cat > "$LAUNCHER_BIN" << 'EOF'
#!/system/bin/sh
# FlowCore Launcher Wrapper
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detectar Python
if command -v python3.13 &> /dev/null; then
    PYTHON="python3.13"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

exec $PYTHON "$BASE_DIR/flowcore.py" "$@"
EOF
    
    chmod +x "$LAUNCHER_BIN"
    log_info "Launcher criado: $LAUNCHER_BIN"
    
    # Tentar copiar para PATH se possível
    if [ -w "/data/data/com.termux/files/usr/bin" ]; then
        cp "$LAUNCHER_BIN" "/data/data/com.termux/files/usr/bin/flowcore" 2>/dev/null || true
        log_info "Comando 'flowcore' disponível globalmente"
    fi
}

# Testar Runtime
test_runtime() {
    log_info "Testando Runtime FlowCore..."
    
    cd "$BASE_DIR"
    
    # Testar imports básicos
    $PYTHON_CMD -c "
import sys
sys.path.insert(0, '$BASE_DIR')

try:
    from FlowCore.Executor.logger import get_logger
    from FlowCore.Executor.permissions import get_permission_manager
    from FlowCore.Executor.shell import ShellRunner
    print('✓ Imports básicos OK')
except Exception as e:
    print(f'✗ Erro nos imports: {e}')
    sys.exit(1)

try:
    logger = get_logger()
    logger.info('Teste de log OK')
    print('✓ Logger OK')
except Exception as e:
    print(f'✗ Erro no logger: {e}')
    sys.exit(1)

try:
    pm = get_permission_manager()
    if pm.validate_command('echo test'):
        print('✓ Permission Manager OK')
    else:
        print('✗ Permission Manager bloqueado')
except Exception as e:
    print(f'✗ Erro no permission manager: {e}')
    sys.exit(1)

try:
    shell = ShellRunner(timeout=10)
    result = shell.execute('echo Hello FlowCore')
    if result.success and 'Hello FlowCore' in result.stdout:
        print('✓ Shell Runner OK')
    else:
        print('✗ Shell Runner falhou')
except Exception as e:
    print(f'✗ Erro no shell runner: {e}')
    sys.exit(1)

print('')
print('Todos os testes passaram! ✓')
"
    
    if [ $? -eq 0 ]; then
        log_info "Runtime testado com sucesso"
    else
        log_error "Falha nos testes do Runtime"
        exit 1
    fi
}

# Iniciar Executor (opcional)
start_executor() {
    echo ""
    read -p "Deseja iniciar o FlowCore agora? (s/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        log_info "Iniciando FlowCore..."
        cd "$BASE_DIR"
        $PYTHON_CMD flowcore.py start
    else
        log_info "FlowCore instalado mas não iniciado"
        log_info "Para iniciar: flowcore start"
    fi
}

# Mostrar informações finais
show_summary() {
    echo ""
    echo "=============================================="
    echo "  ✅ INSTALAÇÃO CONCLUÍDA"
    echo "=============================================="
    echo ""
    echo "Comandos disponíveis:"
    echo "  flowcore start      - Inicia todos os serviços"
    echo "  flowcore stop       - Para todos os serviços"
    echo "  flowcore restart    - Reinicia serviços"
    echo "  flowcore status     - Mostra status"
    echo "  flowcore health     - Health check"
    echo "  flowcore doctor     - Diagnóstico completo"
    echo "  flowcore benchmark  - Roda benchmarks"
    echo "  flowcore optimize   - Otimiza configurações"
    echo "  flowcore logs       - Mostra logs"
    echo "  flowcore repair     - Repara instalação"
    echo ""
    echo "Atalhos:"
    echo "  fc start            - Mesmo que flowcore start"
    echo "  fc status           - Mesmo que flowcore status"
    echo ""
    echo "API: http://127.0.0.1:8765"
    echo "Logs: ~/FlowCore/Logs/"
    echo ""
    echo "Documentação: README.md"
    echo "=============================================="
}

# Main
main() {
    check_termux
    check_python
    install_system_deps
    install_python_deps
    setup_environment
    create_launcher
    test_runtime
    show_summary
    
    # Perguntar se quer iniciar
    start_executor
}

# Executar
main "$@"

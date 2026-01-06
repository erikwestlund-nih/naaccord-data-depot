#!/bin/bash
# NA-ACCORD Development with tmux
# Creates a tmux session with Docker services and useful windows

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="na"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[TMUX]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if tmux is installed
check_tmux() {
    if ! command -v tmux &> /dev/null; then
        error "tmux is not installed"
        echo "Install tmux:"
        echo "  macOS:    brew install tmux"
        echo "  Ubuntu:   sudo apt-get install tmux"
        echo "  RHEL:     sudo yum install tmux"
        exit 1
    fi
}

# Check if session already exists
check_session() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        warn "Session '$SESSION_NAME' already exists"
        echo ""
        read -p "Attach to existing session? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            tmux attach-session -t "$SESSION_NAME"
            exit 0
        else
            read -p "Kill existing session and create new? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                tmux kill-session -t "$SESSION_NAME"
                log "Killed existing session"
            else
                error "Cannot proceed with existing session"
                exit 1
            fi
        fi
    fi
}

# Start Docker services
start_docker_services() {
    log "Starting Docker services..."
    cd "$PROJECT_ROOT"

    # Use the start-dev.sh script to start services
    if [ -f "$SCRIPT_DIR/start-dev.sh" ]; then
        "$SCRIPT_DIR/start-dev.sh" start
    else
        error "start-dev.sh not found"
        exit 1
    fi
}

# Create tmux session
create_tmux_session() {
    cd "$PROJECT_ROOT"

    log "Creating tmux session '$SESSION_NAME'..."

    # Create session with first window (logs)
    tmux new-session -d -s "$SESSION_NAME" -n logs \
        "docker compose -f docker-compose.dev.yml logs -f web services"

    # Window 1: Django web shell
    tmux new-window -t "$SESSION_NAME:1" -n web-shell \
        "docker compose -f docker-compose.dev.yml exec web bash"

    # Window 2: Django services shell
    tmux new-window -t "$SESSION_NAME:2" -n services-shell \
        "docker compose -f docker-compose.dev.yml exec services bash"

    # Window 3: Django shell (interactive Python)
    tmux new-window -t "$SESSION_NAME:3" -n django-shell \
        "docker compose -f docker-compose.dev.yml exec web python manage.py shell"

    # Window 4: Database shell
    tmux new-window -t "$SESSION_NAME:4" -n db \
        "docker compose -f docker-compose.dev.yml exec mariadb mysql -u naaccord -pI4ms3cr3t naaccord"

    # Window 5: Redis CLI
    tmux new-window -t "$SESSION_NAME:5" -n redis \
        "docker compose -f docker-compose.dev.yml exec redis redis-cli"

    # Window 6: Celery logs
    tmux new-window -t "$SESSION_NAME:6" -n celery-logs \
        "docker compose -f docker-compose.dev.yml logs -f celery"

    # Window 7: General bash shell for git and other commands
    tmux new-window -t "$SESSION_NAME:7" -n shell
    tmux send-keys -t "$SESSION_NAME:7" "cd $PROJECT_ROOT" C-m

    # Window 8: Docker compose ps (status monitoring)
    tmux new-window -t "$SESSION_NAME:8" -n status \
        "watch -n 5 'docker compose -f docker-compose.dev.yml ps'"

    # Select the logs window by default
    tmux select-window -t "$SESSION_NAME:0"

    success "tmux session created with 9 windows"
}

# Show session info
show_session_info() {
    echo ""
    echo "============================================="
    success "tmux session '$SESSION_NAME' ready!"
    echo "============================================="
    echo ""
    echo "Windows:"
    echo "  0: logs          - Docker compose logs (web, services)"
    echo "  1: web-shell     - Bash shell in web container"
    echo "  2: services-shell- Bash shell in services container"
    echo "  3: django-shell  - Django Python shell"
    echo "  4: db            - MariaDB client"
    echo "  5: redis         - Redis CLI"
    echo "  6: celery-logs   - Celery worker logs"
    echo "  7: shell         - Local bash shell"
    echo "  8: status        - Service status monitor"
    echo ""
    echo "tmux shortcuts:"
    echo "  Ctrl+b c         - Create new window"
    echo "  Ctrl+b [0-8]     - Switch to window by number"
    echo "  Ctrl+b n         - Next window"
    echo "  Ctrl+b p         - Previous window"
    echo "  Ctrl+b d         - Detach from session"
    echo "  Ctrl+b ?         - Show all key bindings"
    echo ""
    echo "Session commands:"
    echo "  Attach:          tmux attach -t $SESSION_NAME"
    echo "  Detach:          Ctrl+b d"
    echo "  List sessions:   tmux ls"
    echo "  Kill session:    tmux kill-session -t $SESSION_NAME"
    echo ""
}

# Parse command line arguments
COMMAND=${1:-create}

case $COMMAND in
    create|start)
        echo "============================================="
        echo "NA-ACCORD tmux Development Environment"
        echo "============================================="
        echo ""
        check_tmux
        check_session
        start_docker_services
        create_tmux_session
        show_session_info
        log "Attaching to session..."
        tmux attach-session -t "$SESSION_NAME"
        ;;

    attach)
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            tmux attach-session -t "$SESSION_NAME"
        else
            error "No session named '$SESSION_NAME' found"
            echo "Create a new session with: $0 create"
            exit 1
        fi
        ;;

    kill|stop)
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            log "Killing tmux session '$SESSION_NAME'..."
            tmux kill-session -t "$SESSION_NAME"
            success "Session killed"
        else
            warn "No session named '$SESSION_NAME' found"
        fi

        # Also stop Docker services
        read -p "Stop Docker services too? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            "$SCRIPT_DIR/start-dev.sh" stop
        fi
        ;;

    list)
        tmux list-sessions 2>/dev/null || echo "No tmux sessions running"
        ;;

    *)
        echo "Usage: $0 {create|attach|kill|list}"
        echo ""
        echo "Commands:"
        echo "  create   - Create new tmux session with Docker services"
        echo "  attach   - Attach to existing session"
        echo "  kill     - Kill tmux session (optionally stop Docker too)"
        echo "  list     - List all tmux sessions"
        exit 1
        ;;
esac
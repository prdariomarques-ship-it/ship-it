#!/usr/bin/env bash
# First-time setup: creates the docker/.env file and starts the stack.
set -euo pipefail

cd "$(dirname "$0")/../docker"

if [ ! -f .env ]; then
  cp .env.example .env
  JWT_SECRET=$(openssl rand -hex 32)
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=${JWT_SECRET}/" .env
  echo "docker/.env criado com JWT_SECRET gerado automaticamente."
  echo "Edite docker/.env para configurar OPENAI_API_KEY, senha do banco e domínio."
fi

docker compose up -d --build
echo ""
echo "Dario OS está subindo. Endpoints:"
echo "  Dashboard : http://localhost"
echo "  API docs  : http://localhost/docs"
echo "  n8n       : http://localhost/n8n/"

#!/usr/bin/env bash
# Teste de fumaça: sobe-se contra um serviço já rodando e prova que ele responde
# de verdade. Construir a imagem não basta — as armadilhas conhecidas (a
# `RAIZ_PROJETO` calculada do arquivo-fonte, o `static/` que não viaja num
# wheel, o venv que não é relocável) passam pelo build e só quebram na primeira
# requisição.
#
# Uso: scripts/fumaca.sh [URL]   (padrão: http://127.0.0.1:8000)
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
TENTATIVAS="${TENTATIVAS:-30}"

echo "Aguardando ${BASE} responder..."
for _ in $(seq "${TENTATIVAS}"); do
  if curl -fsS -o /dev/null "${BASE}/"; then
    break
  fi
  sleep 1
done

echo "1/4 a página inicial é servida"
curl -fsS "${BASE}/" | grep -q "<title>" 

echo "2/4 os estáticos acompanham a árvore do projeto"
curl -fsS -o /dev/null "${BASE}/static/app.js"
curl -fsS -o /dev/null "${BASE}/static/images/logo.jpeg"

echo "3/4 o preview devolve um PDF"
curl -fsS -X POST "${BASE}/api/preview" \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"numeros","numero_elementos":75,"linhas":5,"colunas":5,"numero_folhas":2,"centro_livre":true}' \
  | head -c 4 | grep -q '%PDF'

# O centro livre desenha o logo padrão, então esta chamada também prova que o
# arquivo de imagem chegou na imagem e que o reportlab consegue abri-lo.
echo "4/4 o jogo completo devolve um PDF"
curl -fsS -X POST "${BASE}/api/jogo" \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"numeros","numero_elementos":75,"linhas":5,"colunas":5,"numero_folhas":2,"centro_livre":true}' \
  | head -c 4 | grep -q '%PDF'

echo "Fumaça: tudo certo."

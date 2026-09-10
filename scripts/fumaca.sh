#!/usr/bin/env bash
# Teste de fumaça: sobe-se contra um serviço já rodando e prova que ele responde
# de verdade. Construir a imagem não basta — as armadilhas conhecidas (a
# `RAIZ_PROJETO` calculada do arquivo-fonte, o `static/` que não viaja num
# wheel, o venv que não é relocável) passam pelo build e só quebram na primeira
# requisição.
#
# Uso: scripts/fumaca.sh [URL]   (padrão: http://127.0.0.1:8000)
#
# Nada de `curl | head`: com `pipefail`, o `head` fecha o cano depois dos
# primeiros bytes, o curl morre de EPIPE e o teste reprova ao acaso — conforme
# a resposta caiba ou não no buffer do pipe. Cada resposta vai para um arquivo
# e é conferida de lá.
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
TENTATIVAS="${TENTATIVAS:-30}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

CONFIG='{"tipo":"numeros","numero_elementos":75,"linhas":5,"colunas":5,"numero_folhas":2,"centro_livre":true}'

falhar() {
  echo "FALHOU: $*" >&2
  exit 1
}

# Baixa uma rota para um arquivo; falha com o código HTTP se não for 2xx.
baixar() {
  local metodo="$1" rota="$2" destino="$3"
  local codigo
  if [ "${metodo}" = "POST" ]; then
    codigo=$(curl -sS -o "${destino}" -w '%{http_code}' \
      -X POST "${BASE}${rota}" \
      -H 'Content-Type: application/json' -d "${CONFIG}") || falhar "${rota}: curl saiu ${?}"
  else
    codigo=$(curl -sS -o "${destino}" -w '%{http_code}' "${BASE}${rota}") \
      || falhar "${rota}: curl saiu ${?}"
  fi
  [ "${codigo}" = "200" ] || falhar "${rota}: HTTP ${codigo}"
}

# Um PDF de verdade: assinatura certa e tamanho plausível, não um erro curto.
conferir_pdf() {
  local arquivo="$1" rota="$2" assinatura tamanho
  assinatura=$(head -c 4 "${arquivo}")
  [ "${assinatura}" = "%PDF" ] || falhar "${rota}: não começa com %PDF (veio '${assinatura}')"
  tamanho=$(wc -c < "${arquivo}")
  [ "${tamanho}" -gt 1000 ] || falhar "${rota}: PDF de apenas ${tamanho} bytes"
  echo "    ${tamanho} bytes de PDF"
}

echo "Aguardando ${BASE} responder (até ${TENTATIVAS}s)..."
pronto=""
for _ in $(seq "${TENTATIVAS}"); do
  if curl -fsS -o /dev/null "${BASE}/" 2>/dev/null; then
    pronto="sim"
    break
  fi
  sleep 1
done
[ -n "${pronto}" ] || falhar "o serviço não respondeu em ${TENTATIVAS}s"

echo "1/4 a página inicial é servida, com a versão injetada"
baixar GET "/" "${TMP}/index.html"
grep -q "<title>" "${TMP}/index.html" || falhar "/: a resposta não parece o index.html"
# A versão sai da metadata do pacote instalado. Na imagem de produção não há
# `pyproject.toml`, então este é o único lugar onde a injeção pode ser provada
# no ambiente que de fato vai para o ar.
grep -qE "Bingo410 v[0-9]" "${TMP}/index.html" || falhar "/: a versão não foi injetada"
! grep -q "{{versao}}" "${TMP}/index.html" || falhar "/: o marcador da versão escapou cru"

echo "2/4 os estáticos acompanham a árvore do projeto"
baixar GET "/static/app.js" "${TMP}/app.js"
baixar GET "/static/images/logo.jpeg" "${TMP}/logo.jpeg"

echo "3/4 o preview devolve um PDF"
baixar POST "/api/preview" "${TMP}/preview.pdf"
conferir_pdf "${TMP}/preview.pdf" "/api/preview"

# O centro livre desenha o logo padrão, então esta chamada também prova que o
# arquivo de imagem chegou na imagem e que o reportlab consegue abri-lo.
echo "4/4 o jogo completo devolve um PDF"
baixar POST "/api/jogo" "${TMP}/jogo.pdf"
conferir_pdf "${TMP}/jogo.pdf" "/api/jogo"

echo "Fumaça: tudo certo."

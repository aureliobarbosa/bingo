#!/usr/bin/env bash
# Configuração de uma vez só do lado do Google, para a Etapa 8.2.
#
# Roda no Cloud Shell (que já tem o gcloud e já está autenticado) ou numa
# máquina com o Google Cloud CLI instalado e `gcloud init` feito:
#
#   git clone https://github.com/aureliobarbosa/bingo.git
#   cd bingo && bash scripts/configura-gcp.sh
#
# É seguro rodar de novo: o que já existe é reaproveitado em vez de virar erro.
# Ao final, imprime os quatro valores que vão para as Variables do repositório
# no GitHub — é só copiar de lá.
set -euo pipefail

PROJETO="${PROJETO:-bingol-508013}"
REGIAO="${REGIAO:-southamerica-east1}"
REPOSITORIO="${REPOSITORIO:-bingo}"
REPO_GITHUB="${REPO_GITHUB:-aureliobarbosa/bingo}"

# Os `create` do gcloud falham quando o recurso já existe. Como o script deve
# poder ser repetido, essa falha específica é tratada como sucesso; qualquer
# outra continua abortando por causa do `set -e`.
criar() {
  local descricao="$1"; shift
  echo "==> ${descricao}"
  if saida=$("$@" 2>&1); then
    printf '%s\n' "${saida}"
  elif printf '%s' "${saida}" | grep -qi "already exists\|ALREADY_EXISTS"; then
    echo "    já existia, seguindo"
  else
    printf '%s\n' "${saida}" >&2
    return 1
  fi
}

command -v gcloud >/dev/null || {
  echo "gcloud não encontrado. Use o Cloud Shell ou instale o Google Cloud CLI." >&2
  exit 1
}

echo "Projeto: ${PROJETO} | Região: ${REGIAO} | Repositório GitHub: ${REPO_GITHUB}"
gcloud config set project "${PROJETO}" >/dev/null
NUMERO_PROJETO="$(gcloud projects describe "${PROJETO}" --format='value(projectNumber)')"

# Sem estas, os comandos seguintes falham com "API not enabled". A sts e a
# iamcredentials são o que o Workload Identity Federation usa para trocar o
# token do GitHub por credencial temporária.
echo "==> Ativando as APIs (demora um pouco na primeira vez)"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project="${PROJETO}"

criar "Repositório de imagens no Artifact Registry" \
  gcloud artifacts repositories create "${REPOSITORIO}" \
    --project="${PROJETO}" --repository-format=docker --location="${REGIAO}" \
    --description="Imagens do gerador de bingo"

# A conta que o CI usa para publicar e implantar.
criar "Conta de serviço do deploy" \
  gcloud iam service-accounts create github-deploy \
    --project="${PROJETO}" --display-name="Deploy pelo GitHub Actions"

# A identidade que o contêiner veste enquanto roda. Fica SEM papel nenhum de
# propósito: o serviço é stateless e não chama nada do Google. Se não existisse,
# o Cloud Run usaria a conta padrão do Compute Engine, que costuma vir com
# poder de Editor sobre o projeto inteiro.
criar "Conta de serviço de execução" \
  gcloud iam service-accounts create bingo-runtime \
    --project="${PROJETO}" --display-name="Identidade do serviço bingo em execução"

SA_DEPLOY="github-deploy@${PROJETO}.iam.gserviceaccount.com"
SA_RUNTIME="bingo-runtime@${PROJETO}.iam.gserviceaccount.com"

echo "==> Papéis da conta de deploy"
gcloud projects add-iam-policy-binding "${PROJETO}" \
  --member="serviceAccount:${SA_DEPLOY}" \
  --role="roles/artifactregistry.writer" --condition=None >/dev/null
gcloud projects add-iam-policy-binding "${PROJETO}" \
  --member="serviceAccount:${SA_DEPLOY}" \
  --role="roles/run.admin" --condition=None >/dev/null

# Para implantar um serviço que roda COMO a bingo-runtime, a conta do CI precisa
# de permissão para agir em nome dela. É o que mais falta na primeira tentativa.
gcloud iam service-accounts add-iam-policy-binding "${SA_RUNTIME}" \
  --project="${PROJETO}" --member="serviceAccount:${SA_DEPLOY}" \
  --role="roles/iam.serviceAccountUser" >/dev/null

criar "Pool de identidades do GitHub" \
  gcloud iam workload-identity-pools create "github" \
    --project="${PROJETO}" --location="global" --display-name="GitHub Actions"

# O --attribute-condition é a peça de segurança: sem ela, QUALQUER repositório
# do GitHub no mundo poderia trocar seu token por acesso a este projeto.
criar "Provedor OIDC preso a ${REPO_GITHUB}" \
  gcloud iam workload-identity-pools providers create-oidc "bingo" \
    --project="${PROJETO}" --location="global" \
    --workload-identity-pool="github" --display-name="Repositório bingo" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository == '${REPO_GITHUB}'" \
    --issuer-uri="https://token.actions.githubusercontent.com"

echo "==> Autorizando o repositório a usar a conta de deploy"
gcloud iam service-accounts add-iam-policy-binding "${SA_DEPLOY}" \
  --project="${PROJETO}" --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${NUMERO_PROJETO}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO_GITHUB}" \
  >/dev/null

# O registro ganha uma imagem por commit; sem política, ele cresce para sempre.
POLITICA="$(dirname "$0")/limpeza-artifact-registry.json"
if [ -f "${POLITICA}" ]; then
  echo "==> Política de limpeza do Artifact Registry"
  gcloud artifacts repositories set-cleanup-policies "${REPOSITORIO}" \
    --project="${PROJETO}" --location="${REGIAO}" --policy="${POLITICA}" >/dev/null
fi

PROVEDOR="$(gcloud iam workload-identity-pools providers describe "bingo" \
  --project="${PROJETO}" --location="global" \
  --workload-identity-pool="github" --format='value(name)')"

cat <<RESUMO

======================================================================
Pronto. Agora cadastre estas quatro Variables no GitHub, em
  Settings -> Secrets and variables -> Actions -> aba Variables
  -> New repository variable

  GCP_PROJECT_ID     ${PROJETO}
  GCP_WIF_PROVIDER   ${PROVEDOR}
  GCP_SA_DEPLOY      ${SA_DEPLOY}
  GCP_SA_RUNTIME     ${SA_RUNTIME}

São identificadores, não credenciais: nenhuma chave foi criada, e nenhum
arquivo de senha precisa existir. Quem autoriza é a condição do provedor,
presa ao repositório ${REPO_GITHUB}.

Depois disso, o próximo push em main implanta sozinho.
======================================================================
RESUMO

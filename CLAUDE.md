# Bingo — gerador de cartelas para impressão

Serviço web que gera cartelas de bingo em PDF, prontas para imprimir. O usuário
define os parâmetros num painel lateral e vê a primeira folha como ela sairá na
impressora. Backend Python + FastAPI + reportlab; frontend Bootstrap 5 e
JavaScript sem build step.

O que falta fazer está em [docs/PLANO.md](docs/PLANO.md). **Leia-o antes de
começar qualquer etapa nova.** O porquê de cada escolha já tomada está em
[docs/DECISOES.md](docs/DECISOES.md): consulte-o ao mexer numa área pronta, sem
precisar lê-lo inteiro (use grep ou sed). As seções abaixo são o resumo dele — uma linha por
decisão.

## Como rodar

```bash
uv sync                                    # cria o ambiente (baixa o Python 3.14)
uv run pytest -q                           # 84 testes
uv run ruff check . && uv run ruff format --check .   # o que o CI cobra
uv run uvicorn bingo.api:app --reload --host 0.0.0.0   # http://localhost:8000
scripts/fumaca.sh http://127.0.0.1:8000    # o serviço responde de verdade
```

O `--host 0.0.0.0` é o que faz o servidor ser alcançável **de fora do
contêiner**, no navegador da máquina. O padrão do uvicorn é `127.0.0.1`, que lá
dentro significa "só o próprio contêiner". O `fumaca.sh` roda de dentro, então
para ele o `127.0.0.1` continua valendo.

Em container (mesma receita para os dois ambientes):

```bash
docker build --target producao -t bingo:producao .   # imagem de produção
docker run -p 8000:8000 bingo:producao
```

O `.devcontainer/` aponta para o estágio `desenvolvimento` do mesmo `Dockerfile`.

O backend de build é o **`uv_build`**, embutido no próprio `uv`. O bloco
`[build-system]` existe porque o layout `src/` precisa dele para o projeto ser
instalado no ambiente (em modo editável) — **não** para publicar nada no PyPI.

O CI (`.github/workflows/ci.yml`) roda esses mesmos comandos em três jobs
paralelos — `testes`, `estatica` e `imagem` — e o último constrói o estágio
`producao`, sobe o container e roda o `scripts/fumaca.sh` contra ele.

## Convenções de trabalho

- **Trunk Based Development**: trabalhar sempre em `main`, sem branches.
- **Um commit por funcionalidade, com os testes junto.** Mensagens em português,
  no imperativo (`feat:`, `docs:`, `chore:`), explicando o *porquê* no corpo.
- **Checkpoints**: ao terminar uma etapa do plano, parar e pedir avaliação do
  usuário antes de seguir para a próxima.
- **Etapa fechada encolhe no plano.** Ao concluir uma etapa, o `PLANO.md` fica
  com o resumo de uma linha por decisão e um ponteiro; o detalhe — comandos,
  armadilhas, medições — vai para `DECISOES.md`. O plano é o que *falta* fazer.
- **Português em tudo**: nomes de funções e variáveis, comentários, mensagens de
  erro e textos da interface.
- **Biblioteca padrão sempre que possível** no backend. O volume de dados é
  pequeno: `random` basta, não usar numpy.
- **Testes básicos por funcionalidade**, cobrindo o caminho principal. Casos de
  borda ficam para depois, por decisão do usuário.

## Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `src/bingo/models.py` | `ConfiguracaoJogo`: dataclass imutável que valida no `__post_init__` e expõe `elementos_por_folha`, `universo`, `indice_centro` |
| `src/bingo/gerador.py` | `gerar_jogo(cfg)` → tupla de folhas distintas; cada folha é uma tupla de células em ordem de leitura, com `None` no centro livre. Sorteia por `random.Random(cfg.semente)` |
| `src/bingo/pdf.py` | Desenho em A4 retrato; `desenhar_folha` é compartilhada por `gerar_pdf_folha` e `gerar_pdf_jogo` |
| `src/bingo/api.py` | Rotas `POST /api/preview` (uma folha) e `POST /api/jogo` (PDF completo), `/static` e `/`, que injeta a versão do pacote na página |
| `static/app.js` | Todo o tráfego HTTP passa pelo objeto `Api`; o resto da interface não conhece o servidor |

Regras de negócio ficam **na dataclass**, não na API: o `ValueError` que ela
levanta vira 422 com a mensagem em português, exibida direto na interface. O
`ConfiguracaoIn` do Pydantic cuida apenas de tipos e faixas.

O serviço é **stateless**: cada requisição traz a configuração completa e recebe
um PDF. Nada é salvo no servidor; a última configuração fica no `localStorage` do
navegador (chaves `bingo.configuracao` e `bingo.tema`) e, de forma durável, num
**arquivo JSON** que o usuário salva e abre pela interface.

O logo enviado pelo usuário viaja como **data URI dentro do JSON**, e não em
`multipart/form-data`: assim o serviço continua stateless, é uma requisição só e
as duas rotas mantêm o mesmo contrato. Ele **não** é gravado no `localStorage` —
alguns MB estourariam a cota e derrubariam o resto da configuração salva. Por
isso, ao recarregar a página, o logo volta a ser o padrão.

## Decisões de produto já fechadas

- Grade de linhas × colunas configuráveis; célula central livre só quando ambas
  forem ímpares, e ela recebe o logo (`static/images/logo.jpeg`).
- Download é um **PDF único multi-página**, uma folha por página.
- **Semente do sorteio** (`semente: int | None`): `random.Random(cfg.semente)` num
  caminho único, sem ramo condicional — com `None` vale a entropia do sistema.
  Como `gerar_jogo` sorteia a primeira folha antes de qualquer descarte por
  repetição, `gerar_folha` com a mesma semente devolve exatamente essa folha: **o
  preview é a primeira página do PDF baixado**, medido byte a byte no fluxo de
  desenho. A faixa para em `2**32-1` porque acima de `2**53` o `Number` do
  JavaScript perde precisão. O botão "Sortear novamente" **troca a semente** —
  sem isso ele redesenharia a mesma cartela.
- **Configuração em arquivo JSON**: `{version: 1, ...configuração, logo_nome}` —
  o mesmo objeto que a API aceita, com o logo como data URI e a semente junto. É
  o caminho durável (o `localStorage` não guarda o logo e some com a limpeza do
  navegador) e vira compartilhamento por e-mail sem custo de código. Tudo no
  frontend: o backend não sabe que o arquivo existe. Importar **não pode
  lançar**, pela mesma razão que `restaurar()` não pode.
- Sorteio com `random.sample`, sem semente fixa por padrão, mas **sem folhas repetidas** dentro de
  um jogo: `gerar_jogo` compara as folhas por `frozenset` e re-sorteia as iguais.
  A folha continua uma tupla ordenada, porque a ordem define a posição na grade.
  Sem isso, um bingo de 12 palavras saía com cartelas idênticas em 64% dos jogos.
- Preview mostra **apenas a primeira folha**, com debounce de 400 ms.
- Bingo de palavras: uma palavra por linha num `<textarea>`.
- Textos com espaço são quebrados em duas linhas, **no espaço mais próximo do
  centro** — sem isso a fonte da folha inteira encolhe por causa do nome mais
  longo.
- **Logo enviado**: só PNG ou JPEG, no máximo 2 MB e 25 megapixels. O limite de
  tamanho existe porque o data URI trafega inteiro a cada atualização do preview;
  o de megapixels trava a imagem pequena que descomprime enorme. `models.py`
  valida o que é barato (cabeçalho do data URI e comprimento do base64) e
  `pdf.py` o que exige abrir a imagem. A margem clara em volta do logo é
  recortada na geração, senão o desenho ocupa ~60% da célula.
- **Limites de entrada**, porque o serviço vai ficar aberto: corpo da requisição
  em 4 MB (413), logo em 2 MB conferidos pelo `max_length` do campo antes de o
  Pydantic materializar a string, e 50 caracteres por palavra — acima disso o
  texto não cabe na célula e encolhe a fonte da folha toda.
- **Universo limitado a 100 elementos** (`MAX_ELEMENTOS` em `models.py`), valendo
  igual para `numero_elementos` e para a quantidade de palavras — são o mesmo
  conceito. Consequência aceita: como a validação exige universo *estritamente
  maior* que os elementos por folha, uma grade de exatamente 100 células (10×10,
  5×20, 20×5) ficou impossível; até 99 células segue valendo.
- **Número de folhas limitado por C(n, k)**, o total de folhas distintas que o
  universo permite: `combinacoes_possiveis` e `maximo_folhas` em `models.py`. O
  JavaScript refaz a conta saturando o produto em `MAX_FOLHAS`, o que dispensa
  `BigInt`. A regra só morde em universos pequenos.
- **A porta do contêiner sai da variável `PORT`**, porque o Cloud Run injeta
  8080 e ignora o `EXPOSE`. Como a forma exec do `CMD` não expande variáveis,
  ele é forma shell — com `exec`, senão o `sh` fica de PID 1 e engole o
  `SIGTERM` do encerramento. O `HEALTHCHECK` lê a mesma variável em Python. O
  uvicorn sobe com `--proxy-headers --forwarded-allow-ips='*'`: sem o
  `X-Forwarded-For`, o limite de taxa por IP da Etapa 8.3 veria todo o tráfego
  como um cliente só.
- **Limite de taxa por IP**: janela deslizante de 60 s, teto de 120 requisições,
  dicionário em memória e biblioteca padrão, só nas rotas `/api/` — os estáticos
  ficam de fora para não gastar a cota de quem só abriu a página. Contém bot em
  laço, não atacante determinado: cada instância tem o seu dicionário, então com
  `--max-instances 3` o teto efetivo é até 3x e zera quando a instância recicla.
- **Cabeçalhos de segurança em toda resposta**, pelo middleware mais externo. A
  CSP dispensa `unsafe-inline` porque a página não tem script nem `style=`
  embutido; ela libera só o jsDelivr (CSS do Bootstrap) e `blob:` em `frame-src`
  e `object-src`, que é como o PDF do preview chega ao `<iframe>`. **Ao mexer no
  frontend, conferir se a CSP ainda cobre o que a página carrega** — o erro é
  silencioso, e só um navegador de verdade responde. O teste severo é o
  **Firefox**: o pdf.js é uma página comum, sujeita à CSP, enquanto o Chrome
  desenha PDF por um visualizador interno que escapa das mesmas diretivas.
- **O timeout de geração é o `--timeout=60s` do Cloud Run.** Um timeout dentro
  do processo não funciona: as rotas são `def` síncronas numa thread do pool, e
  cancelar a tarefa não interrompe a thread — medido, 504 saindo em 3,01 s para
  um trabalho de 3 s com timeout de 0,5 s.
- **A publicação vive no `.github/workflows/deploy.yml`**, separado do `ci.yml`
  porque o WIF exige `id-token: write` e o `ci.yml` roda em pull request — a
  permissão alcançaria código de terceiros. O `deploy.yml` constrói, testa a
  fumaça, empurra ao Artifact Registry e implanta pelo **digest** lido de volta
  do registro, nunca pela tag. Ele se pula sozinho se `vars.GCP_WIF_PROVIDER`
  estiver vazia. Nenhuma chave existe: o WIF troca o token OIDC do GitHub por
  credencial temporária, e `scripts/configura-gcp.sh` recria tudo do lado do
  Google. O serviço roda como `bingo-runtime`, conta **sem papel nenhum**.
- **O endereço público sai do Firebase Hosting** (`bingo410.web.app`, grátis, com
  HTTPS): o domain mapping nativo do Cloud Run está em preview e não vale em
  `southamerica-east1`, e um balanceador custaria ~US$ 18/mês para três
  requisições por dia. O `firebase.json` manda `**` ao serviço e o `public` fica
  vazio de propósito — estático copiado para lá seria servido *antes* do
  rewrite. O deploy do Hosting é manual, de uma vez; o `run.app` continua
  público.
- **Botões do painel todos no mesmo azul** (`btn-primary`), com sombreamento no
  hover tirado de `--bs-emphasis-color-rgb`, que se inverte com o tema. O par
  Números/Palavras fica em contorno: ali o preenchimento é o que marca a
  escolha. O rodapé leva versão, autoria, o ícone do GitHub em SVG embutido
  (a CSP barraria `<img>` de outro domínio) e o link do Lattes.
- **Dependabot diário** (`.github/dependabot.yml`) para `uv` e
  `github-actions`, sem agrupamento e sem auto-merge — num repositório que
  publica em push para `main`, auto-merge seria publicação automática. O
  ecossistema é `uv` e não `pip`: só ele mexe no `uv.lock`. As imagens do
  `Dockerfile` ficaram de fora, e as PRs de *segurança* não saem do arquivo —
  são três chaves em *Settings → Advanced Security*.
- **O repositório é peça de portfólio, sob licença MIT, e não recebe PR da
  comunidade** — o ajuste é do GitHub, em *Settings → General → Features*, e
  não trava clone nem fork. O `README.md` fala com dois leitores, o professor
  que quer usar e quem avalia o trabalho, e não aponta para arquivo nenhum do
  projeto.

## Armadilhas já encontradas

- **Não colocar troca de estado da interface dentro do debounce.** Em
  `static/app.js`, `sincronizarInterface()` responde na hora e só
  `atualizarPreview()` é adiado. Quando os dois estavam juntos, o campo de
  palavras levava 400 ms para aparecer e o clique de edição se perdia.
- **`SVGElement` não tem a propriedade `hidden`** do `HTMLElement`. Para mostrar
  ou esconder um ícone SVG use `toggleAttribute("hidden", ...)`.
- **Ao verificar a interface, medir o efeito, não a intenção**: `getComputedStyle`
  em vez de ler de volta a propriedade que o próprio código acabou de escrever.
- **`RAIZ_PROJETO`** (em `src/bingo/pdf.py`) é calculada a partir do arquivo-fonte,
  então `static/` precisa acompanhar a árvore do projeto — um wheel traz apenas os
  módulos de `src/bingo`, sem `index.html`, `app.js` nem o logo. Por isso a imagem
  copia `src/` e `static/` em vez de instalar o pacote sozinho.
- **No container de desenvolvimento o ambiente fica em `/opt/venv`**, fora do
  diretório montado: dentro dele o `.venv` do host apareceria por cima, com
  caminhos absolutos que não valem no container.
- **O navegador guardava `static/` em cache.** Resolvido na Etapa 8.3: a
  subclasse `EstaticosRevalidados` (em `src/bingo/api.py`) manda
  `Cache-Control: no-cache` e o ETag fecha a revalidação em 304. A armadilha
  fica registrada porque a versão velha do `app.js` já levou a diagnósticos
  errados: se ela reaparecer, confira primeiro se o cabeçalho ainda está lá.
- **Todo arquivo que o `pyproject.toml` referencia precisa entrar no contexto
  do build.** O `license-files = ["LICENSE"]` fez o `uv sync` da imagem falhar
  com *"glob `LICENSE` did not match any files"*: o `Dockerfile` copiava
  `pyproject.toml`, `uv.lock` e `README.md`, e não o `LICENSE`. Passa nos testes
  e na estática, e quebra só no job `imagem` — que foi o que pegou.
- **Mexeu em dependência, rode `uv lock`.** O `pyproject.toml` sozinho deixa o
  `uv.lock` para trás e o `uv lock --check` reprova no primeiro passo do job
  `Testes` — e o `deploy.yml`, que dispara no mesmo push sem depender do
  `ci.yml`, **publicaria assim mesmo**. Quase aconteceu na subida do pillow para
  `>=12.3`, pega antes do push.
- **A versão do uv vive em dois lugares**: o `ARG UV_VERSION` do `Dockerfile` e
  o `env.UV_VERSION` de `.github/workflows/ci.yml`. Elas devem andar juntas,
  senão o CI resolve dependências com uma ferramenta diferente da que constrói
  a imagem.
- **A versão do projeto tem fonte única: o `version` do `pyproject.toml`.** A
  página traz o marcador `{{versao}}` e `index()` o troca ao servir `/`, lendo
  `importlib.metadata.version("bingo")`. Subir de versão é editar essa linha e
  rodar `uv lock`. Ler o `pyproject.toml` em execução **não** funcionaria: ele
  não entra na imagem de produção. E `index()` lê o HTML a cada requisição de
  propósito — guardá-lo em memória quebraria o `--reload`, que observa `.py` e
  não `.html`.
- **`comando | head` sob `set -o pipefail` reprova ao acaso.** O `head` fecha o
  cano e quem escreve morre de EPIPE — mas só quando a saída não cabe no buffer
  de 64 KB do pipe. Foi assim que o `scripts/fumaca.sh` passou localmente e
  quebrou no CI. Escreva num arquivo e confira o arquivo.
- **Nem toda action publica tag móvel de major.** O `astral-sh/setup-uv` parou
  na v7: `@v10` não existe e o job morre no "Set up job". Confira a tag pela API
  (`/repos/<dono>/<repo>/git/ref/tags/<tag>`) antes de escrevê-la no workflow.
- **Construir a imagem não prova que ela funciona.** As armadilhas do
  `RAIZ_PROJETO`, do `static/` e do venv não-relocável passam pelo build e só
  quebram na primeira requisição. Por isso o job `imagem` sobe o container e
  roda o `scripts/fumaca.sh` — que também serve localmente, contra um
  `uvicorn`.
- **As constantes de limite vivem em três lugares** e mudam juntas:
  `src/bingo/models.py` (a autoridade), a constante no topo de `static/app.js` e
  o atributo do campo em `static/index.html`. Vale para `MAX_ELEMENTOS`,
  `MAX_CELULAS`, `MAX_FOLHAS` e `MAX_PALAVRA_CARACTERES`. O `api.py` importa de
  `models.py`, então não conta como quarta cópia. `MAX_SEMENTE` vive em dois
  lugares só: não há campo de semente na tela.
- **PDF do reportlab não é comparável byte a byte**: ele carimba data de criação
  e ID de documento, então dois PDFs do mesmo jogo diferem no arquivo. Para
  comparar, use o texto extraído da página ou
  `page.get_contents().get_data()` (`pypdf`). E **`pdftoppm` nem sempre está
  instalado** — não estava na Etapa 9.
- **Input de arquivo: limpar `value` depois de ler.** Vale para os dois, o do
  logo e o da configuração. Sem isso, escolher o mesmo
  arquivo outra vez não dispara `change` e a interface parece morta — isso já
  custou uma sessão inteira de diagnóstico. E **não aninhe o `<input>` dentro do
  `<label>`** que serve de botão: o clique borbulha de volta ao label, que o
  reencaminha, e o comportamento varia entre navegadores.
- **`restaurar()` (em `static/app.js`) não pode lançar.** Se lançar, a
  inicialização morre no meio — sem preview, sem eventos ligados e sem saída pela
  interface, já que não existe botão de restaurar padrões (dispensado no item
  6.1.4 de `docs/DECISOES.md`, com o motivo registrado lá).
- **Ao trocar o preview, não revogar a URL do blob na hora.** Se o navegador
  estiver configurado para baixar PDF em vez de exibir (no Firefox, o tipo
  `application/pdf` como "Salvar arquivo"), o diálogo de download fica apontando
  para uma URL já revogada e salva um **arquivo vazio**. `exibirPdf` em
  `static/app.js` revoga a anterior no `load` do `iframe`, com tempo limite para
  não vazar quando o `load` nunca vem — que é justamente o caso do download.
- **Chrome headless não renderiza PDF** dentro de `iframe`; o `iframe` aparece
  preto nos screenshots mesmo com tudo funcionando. Verifique pelo DOM
  (`preview.src` começa com `blob:`). **Firefox headless não roda neste ambiente**
  (trava até o timeout, inclusive em `about:blank`).
- **Atrás do Firebase Hosting o IP do cliente vem em `Fastly-Client-Ip`.** Quem
  fala com o Cloud Run é a CDN, então o `request.client` seria o mesmo para todo
  mundo e o limite de taxa viraria um teto global. `_cliente()` (em
  `src/bingo/api.py`) lê o cabeçalho primeiro e só depois cai para a conexão.
- **403 do `projects:addfirebase` costuma ser aceitação de termos, não papel
  faltando.** Se `GET /v1beta1/availableProjects` responde 200 listando o projeto
  e o `POST :addFirebase` dá 403 com a conta em `roles/owner`, é gate de conta:
  criar um projeto qualquer pelo console do Firebase apresenta os termos e
  destrava. O diagnóstico inteiro está em `docs/DECISOES.md`.
- **Nome de site do Hosting: só o `sites:create` decide.** `bingo` e
  `teacher-bingo` respondiam "Site Not Found" por HTTP e mesmo assim estavam
  reservados; o que valeu foi `bingo410`.

## Desempenho medido

Medidas do container local e, depois, do serviço já publicado:

| Medida | Container local | Cloud Run |
|---|---|---|
| Memória em uso | 47 MB | — |
| Partida a frio até responder | 2,8 s | 2,56 s (após 17 min ocioso) |
| Requisição com a instância quente | — | 0,25 s |
| Gerar 100 folhas (o pedido mais caro) | 0,38 s | 0,67 s pela rede |
| Imagem de produção | 382 MB | — |

A partida a frio quase igual nos dois lados indica que o tempo é do processo
subindo (Python, FastAPI, reportlab), não da infraestrutura alocando instância.

## Verificação da interface sem navegador interativo

O padrão que funcionou: copiar `static/index.html` para um arquivo temporário com
um `<script>` extra ao final, que dirige o formulário e imprime o resultado num
`<pre>`; depois ler com `google-chrome --headless --dump-dom`. Apagar os arquivos
temporários em seguida. Para conferir o PDF impresso, `pdftoppm -png` e ler a
imagem.

**O Chrome nem sempre está instalado** — não estava no ambiente da Etapa 6.3.
Confirme antes (`which google-chrome chromium`) em vez de concluir que a página
quebrou. Sem ele, para checar a *lógica* de validação basta o Node: avaliar
`static/app.js` com `vm.runInContext` num contexto que traz um `document`
mínimo (`getElementById` devolvendo um objeto com `value`, `textContent`,
`hidden`, `addEventListener` e afins, mais `querySelector`, `localStorage`,
`fetch` e `URL`), e então chamar `validar(cfg)` direto. Não substitui o
navegador para layout ou eventos, mas prova que frontend e `models.py` dão a
mesma mensagem para a mesma configuração. A chamada final a `atualizarPreview()`
rejeita sozinha nesse contexto — é ruído esperado, não falha do teste.

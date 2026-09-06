# Bingo — decisões tomadas e por quê

Registro do que já foi resolvido, para consulta na hora de mexer numa área
pronta. **Não é um histórico**: a cronologia está no `git log`, com datas,
autoria e diffs. O que vive aqui é o *porquê* — a alternativa descartada, a
medição que sustentou a escolha, a armadilha que motivou o desenho atual.

O resumo de uma linha por decisão está no [CLAUDE.md](../CLAUDE.md); este arquivo
é a profundidade por trás dele. O que ainda falta fazer está em
[PLANO.md](PLANO.md).

As seções abaixo mantêm a numeração das etapas e o texto escrito na época de
cada uma, inclusive as previsões que a execução depois corrigiu — a correção fica
anotada no próprio item, que é o que dá para ler a decisão junto com o seu
desfecho.

> **Duas linhas da tabela de enquadramento abaixo foram superadas** e ficam como
> registro do ponto de partida, não do estado atual: o **logo** deixou de estar
> fora do protótipo (etapas 6.1.1 a 6.1.3.v) e o **sorteio** deixou de ser
> `random.sample` simples, passando a evitar folhas repetidas (etapa 6.1.7).

## Contexto

O repositório estava vazio quando este plano foi escrito (scaffold `uv`, sem nenhum
commit ainda). O objetivo é um
protótipo simples porém bem estruturado de um gerador de cartelas de bingo para
impressão: o usuário define os parâmetros do jogo num painel lateral, vê o
resultado como ele sairá impresso, e baixa um PDF pronto para imprimir. O serviço
deve poder ir para produção depois, então a arquitetura é *stateless* e sem banco.

Decisões já fechadas com o usuário:

| Tema | Decisão |
|---|---|
| Grade | Linhas × colunas configuráveis, com opção de célula central livre (só quando L e C forem ímpares) |
| Saída | PDF único multi-página, 1 folha por página |
| Logo | Fora do protótipo — cabeçalho tem apenas título/subtítulo em texto |
| Frontend | Bootstrap 5 (CDN) + JavaScript vanilla, sem build step |
| Sorteio | `random.sample` simples, sem checagem de duplicatas nem semente |
| Preview | Apenas a primeira folha, atualizada a cada mudança de parâmetro |
| Palavras | `<textarea>`, uma palavra por linha |
| Estado | Stateless: nada salvo no servidor |

### Sobre a escolha de frontend (crítica pedida)

Bootstrap 5 + JS vanilla é a escolha **certa** aqui, e não apenas a mais fácil.
A interface é um formulário e um visualizador — não há estado compartilhado
complexo, roteamento nem listas dinâmicas que justifiquem React/Vue. Bootstrap
entrega grid responsivo, formulários e feedback de validação prontos, sem Node,
sem bundler e sem pipeline de build no deploy: os arquivos são servidos
estaticamente pelo próprio FastAPI, e o deploy continua sendo um único container.
Se mais tarde a interface crescer (múltiplos jogos salvos, edição em lista),
Alpine.js pode ser adicionado via CDN sem reescrever nada — é uma porta aberta,
não uma decisão que precisa ser tomada agora.

## Estrutura de arquivos

```
bingo/
├── pyproject.toml            # deps: fastapi, uvicorn, reportlab, pydantic; dev: pytest, httpx, pypdf
├── README.md                 # como rodar e como fazer deploy
├── src/bingo/
│   ├── __init__.py
│   ├── models.py             # ConfiguracaoJogo + validação
│   ├── gerador.py            # gerar_jogo()
│   ├── pdf.py                # gerar_pdf_folha(), gerar_pdf_jogo()
│   └── api.py                # app FastAPI
├── static/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── tests/
    ├── test_models.py
    ├── test_gerador.py
    ├── test_pdf.py
    └── test_api.py
```

`main.py` na raiz (hello-world do scaffold) é removido.


---

## Etapa 0 — Setup

1. Preencher `pyproject.toml`: layout `src/`, dependências e `[dependency-groups] dev`.
2. Acrescentar ao `.gitignore`: `.pytest_cache/`, `*.pdf`.
3. `uv sync` e verificar que `reportlab` instala sob Python 3.14.
   - **Risco:** se `reportlab` ainda não publicar wheel para 3.14, baixar
     `requires-python` e `.python-version` para `3.12` (versão do sistema). Decidir
     na primeira execução do `uv sync`, não antes.
4. Commit: `chore: estrutura inicial do projeto`.

## Etapa 1 — Modelo e validação (`src/bingo/models.py`)

`ConfiguracaoJogo` como `dataclass(frozen=True)`:

```
tipo: Literal["numeros", "palavras"]
numero_elementos: int          # só para tipo="numeros"; universo = 1..numero_elementos
palavras: tuple[str, ...]      # só para tipo="palavras"
linhas: int
colunas: int
numero_folhas: int
centro_livre: bool
titulo: str
subtitulo: str
```

Propriedades derivadas:
- `elementos_por_folha` = `linhas * colunas - (1 if centro_livre else 0)`
- `universo` → `tuple(range(1, numero_elementos + 1))` formatado como texto, ou `palavras`
- `indice_centro` → posição da célula central na ordem de leitura, ou `None`

`validar()` (chamada no `__post_init__`) levanta `ValueError` com mensagem em
português para cada regra:
- `linhas`, `colunas` ≥ 1; `linhas * colunas` ≤ 100 (sanidade de impressão)
- `centro_livre` exige `linhas` e `colunas` ímpares
- `len(universo) > elementos_por_folha` — regra explícita do usuário
- `1 ≤ numero_folhas ≤ MAX_FOLHAS` — teto de proteção para o serviço online
  (500 no plano original; hoje 100, decidido durante a execução)
- tipo `palavras`: nenhuma palavra vazia depois de `strip()`; sem duplicatas
- tipo `numeros`: `numero_elementos ≥ 1`

Testes (`tests/test_models.py`): um caso válido de cada tipo; um `pytest.raises`
para cada regra acima.

Commit: `feat: modelo de configuração do jogo com validação`.

## Etapa 2 — Gerador de folhas (`src/bingo/gerador.py`)

```python
def gerar_jogo(cfg: ConfiguracaoJogo) -> tuple[tuple[str | None, ...], ...]:
    """Devolve uma tupla de folhas; cada folha é uma tupla de células em ordem
    de leitura (esquerda→direita, cima→baixo). None marca a célula central livre."""
```

Implementação: para cada folha, `random.sample(cfg.universo, cfg.elementos_por_folha)`
e, se `centro_livre`, inserir `None` em `cfg.indice_centro`. Apenas biblioteca
padrão (`random`), conforme pedido.

Testes (`tests/test_gerador.py`):
- número de folhas gerado = `numero_folhas`
- cada folha tem `linhas * colunas` células
- todas as células (exceto `None`) pertencem ao universo
- não há repetição dentro de uma mesma folha
- com `centro_livre=True`, a célula do meio é `None` e as demais não são
- funciona igual para tipo `palavras`

Commit: `feat: geração das folhas do jogo`.

## Etapa 3 — Renderização em PDF (`src/bingo/pdf.py`)

Usar `reportlab.pdfgen.canvas` em A4 retrato — controle direto sobre a grade é
mais simples aqui do que Platypus.

```python
def desenhar_folha(c, folha, cfg, indice, total) -> None   # desenha na página atual
def gerar_pdf_folha(folha, cfg, indice=1, total=1) -> bytes  # PDF de 1 página
def gerar_pdf_jogo(folhas, cfg) -> bytes                     # PDF multi-página
```

`gerar_pdf_jogo` cria um `canvas` sobre um `io.BytesIO`, chama `desenhar_folha`
para cada folha e `c.showPage()` entre elas — as três funções compartilham o
mesmo código de desenho, sem duplicação.

Layout de cada página:
- margens fixas; cabeçalho com `titulo` (destaque) e `subtitulo`
- grade ocupando o espaço restante, células de tamanho uniforme, linhas de borda
- tamanho da fonte da célula calculado a partir da largura da célula e do maior
  texto da folha (`c.stringWidth`), para que palavras longas não estourem
- célula central livre desenhada vazia (fundo cinza claro)
- rodapé `Folha i de N`

Testes (`tests/test_pdf.py`), usando `pypdf` para inspecionar a saída:
- `gerar_pdf_folha` produz bytes que começam com `%PDF` e têm 1 página
- `gerar_pdf_jogo` produz o mesmo número de páginas que folhas
- o texto de uma célula aparece no texto extraído da página (tipo `palavras`)

Commit: `feat: renderização das folhas em PDF`.

## Etapa 4 — API (`src/bingo/api.py`) → **checkpoint: avaliação do backend**

Modelo Pydantic `ConfiguracaoIn` espelhando os campos, convertido para
`ConfiguracaoJogo` num único ponto; `ValueError` da dataclass é traduzido para
`HTTPException(422, detail=...)` por um `exception_handler`, de modo que a
mensagem em português chegue ao frontend.

| Rota | Método | Resposta |
|---|---|---|
| `/api/preview` | POST | `application/pdf` — apenas a primeira folha |
| `/api/jogo` | POST | `application/pdf` com `Content-Disposition: attachment; filename=bingo.pdf` |
| `/static/*` | GET | arquivos estáticos (`StaticFiles`) |
| `/` | GET | `static/index.html` |

CORS não é necessário (mesma origem). Testes (`tests/test_api.py`) com
`TestClient`: preview retorna 200 + `application/pdf`; jogo retorna 200 e
contém N páginas; configuração inválida retorna 422 com mensagem.

Commit: `feat: API FastAPI para preview e download do jogo`.

**Parar aqui e pedir avaliação do usuário.**

## Etapa 5 — Frontend desconectado → **checkpoint: avaliação do frontend**

`static/index.html`: Bootstrap 5 por CDN, `container-fluid > row`:
- **Coluna esquerda** (`col-lg-4`, `position-sticky` em telas grandes): formulário
  com título/subtítulo, seletor de tipo (números | palavras), campo de número de
  elementos *ou* `<textarea>` de palavras (alternados por JS), linhas, colunas,
  checkbox de centro livre (desabilitado quando L ou C for par), número de folhas,
  área de mensagens de erro (`alert alert-danger`) e botão de download.
- **Coluna direita** (`col-lg-8`): `<iframe>` com o PDF da primeira folha, em
  proporção A4. Em telas pequenas as colunas empilham naturalmente (form em cima).

`static/app.js`: leitura do formulário → objeto de configuração; validações de
UI espelhando as do backend; `debounce` de 400 ms nas mudanças; troca do
`iframe.src` por `URL.createObjectURL(blob)`, revogando a URL anterior;
persistência dos últimos parâmetros em `localStorage`.

Todo o acesso ao servidor fica isolado em um objeto `Api` no topo de `app.js`,
com dois métodos: `preview(cfg)` e `baixarJogo(cfg)`. **Nesta etapa** eles
retornam um PDF de exemplo estático (`static/exemplo.pdf`, gerado uma vez pelo
próprio backend e commitado), o que permite construir e revisar toda a interface
sem depender do servidor.

Commit: `feat: interface web com Bootstrap (sem backend)`.

**Parar aqui e pedir avaliação do usuário.**

## Etapa 6 — Conexão frontend ↔ backend → **checkpoint: avaliação dos conectores**

Substituir o corpo dos dois métodos de `Api` por `fetch` real contra
`/api/preview` e `/api/jogo`; tratar resposta 422 lendo o `detail` e exibindo-o
no alerta; estado de "gerando…" no painel de preview; `baixarJogo` cria um link
temporário para forçar o download. Remover `static/exemplo.pdf`.

Verificação manual: subir o servidor, mudar cada parâmetro e ver o preview
atualizar; provocar um erro de validação (elementos ≤ elementos por folha) e ver
a mensagem; baixar o PDF e conferir a contagem de páginas.

Commit: `feat: conecta interface ao backend`.

**Parar aqui e pedir avaliação do usuário.**

## Etapa 6.1 — Refinamentos

Ajustes identificados durante a execução, todos pequenos e independentes entre si.

### 6.1.1 Recorte automático da margem do logo

O logo ocupa 88% da célula central, mas o arquivo tem margem branca própria, então
o desenho aparece com cerca de 60% do lado da célula. Recortar a borda uniforme na
geração (`Image.getbbox()` sobre a imagem invertida, com PIL, que já vem instalado
como dependência do reportlab) faz o logo preencher a célula de verdade. Vale para
qualquer logo, não só o atual. O recorte é calculado uma vez e reaproveitado entre
as folhas, não a cada página.

Arquivo: `src/bingo/pdf.py` (`_desenhar_logo`).

### 6.1.2 Controle do logo na interface

Hoje o logo aparece sempre que há célula central livre, é sempre o mesmo arquivo e
não há como desligá-lo. Acrescentar no painel um seletor com três opções:

- **sem logo** — a célula central fica cinza, como antes;
- **logo padrão** — `static/images/logo.jpeg`;
- **enviar imagem** — o usuário escolhe um arquivo próprio.

### 6.1.3 Botão de personalizar o logo (envio de imagem)

O envio da imagem quebra a simetria atual da API, em que toda requisição é JSON e o
serviço é stateless. Duas saídas, a decidir na implementação:

- **imagem embutida no JSON** como data URI (base64), mantendo uma só requisição e
  o serviço sem estado — mais simples, custo de ~33% no tamanho do corpo;
- **`multipart/form-data`** nas duas rotas, mais convencional para upload.

Em ambos os casos é preciso validar formato (PNG/JPEG), dimensões e tamanho máximo,
já que o serviço vai ficar exposto na internet — ver as questões de segurança da
Etapa 8.

### 6.1.3.v Validação do arquivo enviado

Hoje só há duas checagens: o data URI precisa começar com `data:image/` e a
imagem precisa ser legível pelo PIL. Falta limitar **formato** (PNG e JPEG),
**dimensões** e **tamanho máximo** — sem teto, uma imagem de dezenas de MB é
aceita e trafega inteira a cada atualização do preview. Validar no backend, que é
a autoridade, e também no frontend, para avisar antes de enviar.

### 6.1.4 Botão "Restaurar padrões" — **dispensado**

Descartado por decisão do usuário, com o motivo registrado para não ser reaberto
por engano: **nenhum estado salvo deixa o usuário preso**. Todos os campos são
editáveis na tela e a validação impede salvar configuração inválida, então
restaurar padrões seria conveniência, não recuperação — e um controle a mais
competindo por atenção num painel que já tem quatro blocos e três botões.

Em troca, `restaurar()` em `static/app.js` foi blindada: o preenchimento inteiro
fica dentro de um `try` e, diante de estado salvo ilegível ou de outro formato,
cai para os padrões do HTML. Sem isso, um `localStorage` com formato inesperado
mataria a inicialização no meio — sem preview, sem eventos ligados e sem saída
pela interface, que é o único cenário em que o botão faria falta (e no qual ele
também já não funcionaria).

### 6.1.5 Limitar o número de folhas às combinações possíveis (backend)

Hoje o número de folhas é limitado apenas pelo teto `MAX_FOLHAS`. Ele deve
passar a ser limitado também pela quantidade de folhas distintas que o universo
permite formar.

**Expressão a implementar** — folhas tratadas como *conjuntos* de elementos, isto é,
duas folhas com os mesmos elementos em ordens diferentes contam como uma só:

```
                        n!
máximo de folhas = C(n, k) = ─────────────
                     k! · (n − k)!
```

com `n = len(cfg.universo)` (elementos disponíveis) e `k = cfg.elementos_por_folha`
(células sorteadas, já descontando o centro livre). Em Python é `math.comb(n, k)`,
da biblioteca padrão.

O limite efetivo passa a ser `min(MAX_FOLHAS, math.comb(n, k))`, e a validação vive
em `ConfiguracaoJogo.validar()`, como as demais regras.

**Verificação manual — confirmada pelo usuário.** A interpretação é a combinação:
folhas com os mesmos elementos em ordens diferentes são a mesma folha. Os problemas
só aparecem quando o universo é pequeno ou quando `k` está próximo de `n`.

Valores conferidos, calculados com `math.comb`:

   | n | k | C(n, k) |
   |---|---|---|
   | 9 | 8 | 9 |
   | 10 | 8 | 45 |
   | 20 | 16 | 4.845 |
   | 50 | 24 | ≈ 1,2 × 10¹⁴ |
   | 75 | 24 | ≈ 2,6 × 10¹⁹ |

**Observação sobre o alcance real da regra.** Em grades comuns o número de
combinações é astronômico, então quem limita continua sendo `MAX_FOLHAS`. A nova
regra só morde em universos pequenos — por exemplo 9 elementos numa grade 3×3 com
centro livre, onde existem apenas 9 folhas distintas possíveis.

**Ponto a decidir junto:** o gerador hoje faz sorteio simples e *não* verifica se
duas folhas saíram iguais (decisão da Etapa 2). O limite `C(n, k)` impede pedir mais
folhas do que existem combinações, mas não garante que as folhas geradas sejam
distintas entre si. Garantir isso é uma mudança adicional no gerador — decidir se
entra junto ou fica para depois.

### 6.1.6 Mostrar o máximo de folhas na interface

O rótulo do campo de número de folhas passa a exibir o valor calculado em 6.1.5,
recalculado a cada mudança de parâmetro:

```
Número de folhas: (de {maximo_folhas}
```

**Texto a fechar com o usuário:** o parêntese fica aberto na especificação. Formas
possíveis: `Número de folhas (máximo: {maximo_folhas})` ou
`Número de folhas (de 1 a {maximo_folhas})`.

O cálculo precisa existir nos dois lados: no backend, como validação, e no frontend,
para exibir o número sem ida ao servidor.

**Decidido com o usuário:** no JavaScript o cálculo satura em **1000 folhas** — ao
atingir esse valor, para de multiplicar e devolve 1000. Isso dispensa `BigInt` e
resolve o estouro de `Number.MAX_SAFE_INTEGER` (C(75, 24) ≈ 2,6 × 10¹⁹). O contexto
de uso justifica: a maior turma da escola tem 30 alunos e a escola inteira, 200.

**Resolvido:** `MAX_FOLHAS` passou a ser 100, no backend e no frontend, e é o teto
único dos dois lados. Com isso o cálculo em JavaScript não precisa de `BigInt`:
basta parar de multiplicar ao passar de `MAX_FOLHAS`.

Arquivos: `static/index.html` e `static/app.js`.

### 6.1.7 Avaliar conjuntos no lugar de tuplas para as folhas

Avaliação de estrutura de dados, motivada pelos dois itens acima. Usar `frozenset`
para representar o conteúdo de uma folha torna natural o que hoje é trabalhoso:

- comparar duas folhas ignorando a ordem dos elementos, que é exatamente a noção de
  "folha repetida" adotada em 6.1.5;
- detectar folhas idênticas em tempo constante, guardando as já sorteadas num
  conjunto de `frozenset`, em vez de comparar par a par.

**Restrição a respeitar:** a folha também precisa manter a **ordem** das células,
porque é ela que define a posição de cada elemento na grade impressa e a posição do
centro livre. Um conjunto sozinho perde essa informação. O desenho provável é
manter a tupla ordenada como a representação da folha e usar `frozenset` apenas como
chave de comparação, não como substituto.

Avaliar também o `universo` em `ConfiguracaoJogo`: a checagem de palavras repetidas
já constrói um `set` a cada validação.

**Concluído.** A avaliação mostrou que o `frozenset` só teria valor se o gerador
passasse a evitar folhas repetidas — e a medição mostrou que ele precisa: com 12
palavras numa grade 3x3, **64% dos jogos saíam com duas cartelas idênticas**, e com
9 palavras, 100%. Duas cartelas iguais significam dois vencedores simultâneos com a
mesma jogada. Em bingos de números a repetição nunca ocorre, porque as combinações
são astronômicas.

`gerar_jogo` passou a comparar as folhas por `frozenset` e re-sortear as iguais,
mantendo a tupla ordenada como representação — a ordem define a posição na grade.
O limite C(n, k) da 6.1.5 é o que torna isso seguro; há ainda um teto de tentativas
como trava. Custo medido: 2,1 ms no pior caso (100 folhas de 75 números).

Commit por item, como nas demais etapas.

**Parar aqui e pedir avaliação do usuário.**

## Etapa 6.2 — Limites de entrada que faltavam — **concluída**

Levantada ao conferir contra o código um briefing sobre a publicação, que
apontava "número máximo de palavras por requisição" como a única pendência de
validação. Eram três, e com uma causa-raiz comum: **nada limitava o tamanho do
corpo da requisição**, então ele era lido inteiro na memória antes de qualquer
checagem.

| Entrada | Antes | Agora |
|---|---|---|
| Corpo da requisição | sem limite | 4 MB, com 413 |
| `logo_enviado` | 2 MB, conferidos em `models.py` | `max_length` no campo, antes do Pydantic materializar |
| Cada palavra | sem limite | 50 caracteres |

O teto de 4 MB vem do pior caso legítimo: um logo de 2 MB vira ~2,8 MB em
base64, mais palavras e cabeçalho. O Cloud Run corta em 32 MiB; este é o limite
da aplicação, mais apertado.

**O middleware confere o `Content-Length`**, que é o que todo cliente honesto
manda. Uma requisição em `chunked`, sem esse cabeçalho, escapa da checagem —
fica contida pelos tetos de cada campo e pelo limite da plataforma. Contar bytes
durante o streaming resolveria, e foi considerado desproporcional para o risco.

**O limite do logo mudou de lugar, não de valor.** Os 2 MB já existiam em
`_validar_logo`, mas só rodavam depois de o Pydantic construir a string inteira
— tarde demais para servir de proteção. O `max_length` no campo é derivado de
`MAX_LOGO_BYTES`, então continua havendo um só número a mudar.

**As 50 letras por palavra são regra de impressão**, não de segurança: acima
disso o texto não cabe na célula e encolhe a fonte da folha inteira, que é a
mesma razão da quebra em duas linhas já registrada. Validado nos dois lados.

O teto de *quantidade* de palavras não entrou aqui: é o tamanho do universo, e
foi tratado junto com `numero_elementos` na 6.3.

## Etapa 7 — Container — **concluída**

`Dockerfile` com três estágios e um `.devcontainer/devcontainer.json` que aponta
para o de desenvolvimento, de modo que o ambiente de trabalho e o de produção
saiam da mesma receita.

| Estágio | Base | Para quê |
|---|---|---|
| `desenvolvimento` | imagem do `uv` | devcontainer: código montado, grupo dev, `--reload` |
| `construcao` | imagem do `uv` | monta o ambiente a partir do `uv.lock` |
| `producao` | `python:3.14-slim` | recebe só o `.venv` pronto, `src/` e `static/` |

**Decisões tomadas na execução:**

- **`static/` continua fora do pacote**, e a imagem copia a árvore do projeto.
  Confirmado na prática: `uv build` gera um wheel com apenas os cinco módulos de
  `src/bingo`, sem `index.html`, `app.js` nem o logo. Mover `static/` para dentro
  do pacote foi descartado por não trazer ganho.
- **Produção não tem `uv`**: o ambiente é montado no estágio `construcao` e
  copiado pronto. Tirou 77 MB (459 MB → 382 MB) e reduz a superfície de ataque.
- **No desenvolvimento o ambiente vive em `/opt/venv`**, fora do diretório
  montado. Dentro dele, o `.venv` do host apareceria por cima do ambiente do
  container, com caminhos absolutos que não valem lá.
- Roda como usuário sem privilégios (uid 1000) e tem `HEALTHCHECK`.

**Verificado:** os 52 testes passam dentro do estágio de desenvolvimento com o
código montado; em produção o container serve `/`, `/static/images/logo.jpeg` e
gera um PDF de 5 páginas com o logo na célula central; o healthcheck reporta
`healthy`.

### 7.1 Ferramentas de trabalho dentro do devcontainer — **concluída**

Duas faltas percebidas ao usar o container no dia a dia, ambas de ambiente, sem
efeito sobre produção:

- **`git` não existia no container.** A imagem base do `uv` não o traz e o
  `Dockerfile` instalava apenas `ca-certificates`, `curl`, `gnupg` e `nodejs`.
  O `.git/` chegava pelo *bind mount* de `/app`, mas não havia binário para
  lê-lo: `git: command not found` no terminal. Resolvido acrescentando `git` ao
  `apt-get install` do estágio `desenvolvimento`.
- **A extensão do Claude Code não era instalada.** Extensões do host não são
  herdadas pelo devcontainer; precisam estar declaradas em
  `customizations.vscode.extensions`. Acrescentado `anthropic.claude-code` à
  lista, ao lado de `ms-python.python` e `charliermarsh.ruff`.

Junto veio o **mount do `~/.gitconfig`** (`/root/.gitconfig`), no mesmo padrão
dos mounts de `~/.claude` — sem ele o git dentro do container fica sem
`user.name`/`user.email` e todo commit falha. A escolha do mount em vez de
configurar a identidade dentro do container só é segura porque **há um único
desenvolvedor**: se o arquivo não existir no host, o Docker cria um diretório
vazio no lugar e o git passa a reclamar.

Como o `git` vem de uma camada nova da imagem, as mudanças exigem **Rebuild
Container** — reabrir não basta.

**`safe.directory` — não é necessário, e o motivo é verificável.** O `/app` chega
por *bind mount*; quando o dono dos arquivos no host tem UID diferente do usuário
do container, o git recusa a operação com *"detected dubious ownership in
repository at '/app'"*. Decidiu-se, na hora, aguardar o sintoma em vez de
adicionar a exceção preventivamente — desligar uma proteção sem evidência de que
faça falta. O sintoma não apareceu, e a medição explica por quê: `/app` e
`/app/.git` pertencem a `0:0` e o container roda como `root`, então os UIDs
coincidem e a checagem do git nunca dispara.

Fica registrado porque a conclusão vale para **esta** configuração, não em geral:
voltaria a morder num host cujo UID não fosse 0 ou num container que rodasse como
usuário sem privilégios — como o estágio `producao` já faz. A correção, se um dia
for preciso, é uma linha: `git config --global --add safe.directory /app`, no
`postCreateCommand`.

Commit: `chore: ferramentas de trabalho dentro do devcontainer`.

### 7.2 Base única nos três estágios e versão do uv fixada — **concluída**

Revisão da escolha de imagem, motivada pela pergunta de por que o projeto usava
uma imagem da Astral. A investigação dentro do próprio container mostrou que
`ghcr.io/astral-sh/uv:python3.14-bookworm-slim` **não traz um Python próprio da
Astral**: as variáveis `PYTHON_VERSION`/`PYTHON_SHA256`, o layout `/usr/local`
com `pip`, `idle` e `pydoc`, e o `CONFIG_ARGS`
(`--enable-optimizations --with-lto --enable-shared`) são os do
`docker-library/python`. `/root/.local/share/uv/python/` nem existe. Era, o tempo
todo, o `python:3.14-slim-bookworm` com o binário do uv por cima — a mesma base
de `producao`.

Então a escolha estava certa, mas tinha uma folga: a tag não nomeia a versão do
uv. O `uv.lock` fixa as dependências, e a ferramenta que o lê flutuava a cada
rebuild. Os estágios `desenvolvimento` e `construcao` passaram a ser
`python:3.14-slim-bookworm` mais `COPY --from=uv /uv /uvx /bin/`, com a versão
num `ARG UV_VERSION` único (0.9.30, a que já estava em uso — a troca é neutra em
comportamento).

**A invariante que isso torna explícita**, e que era coincidência antes:
`producao` recebe o `.venv` pronto de `construcao`, e **um venv não é relocável
entre instalações diferentes de Python**. Ele grava o caminho absoluto do
interpretador — `home = /usr/local/bin` no `pyvenv.cfg`, e `bin/python` é symlink
para `/usr/local/bin/python3` — e carrega extensões compiladas contra uma libc
(`cpython-314-x86_64-linux-gnu`). A cópia entre estágios só funciona porque as
bases coincidem; com a base unificada, isso deixa de depender de a Astral
continuar montando a imagem dela sobre a oficial.

**Alpine foi avaliado e descartado.** É a troca de base mais tentadora para
reduzir os 382 MB, e é exatamente a que quebra a invariante acima: musl muda a
ABI, o `.venv` de `construcao` deixa de servir em `producao` e pillow e reportlab
passam a depender de wheels musllinux. Com a carga projetada nesta etapa 8
(2,7 requisições por dia), otimizar o tamanho da imagem é resolver um problema
que não existe.

Ganhos práticos: uma imagem base baixada em vez de duas em cada máquina, melhor
reaproveitamento de cache no CI da 8.1, e subir de versão do Python vira uma
linha em vez de duas em imagens diferentes.

Exige **Rebuild Container**: mudar o `FROM` invalida toda a cadeia de camadas.
Os `--mount=type=cache` do uv sobrevivem (são caches do BuildKit, não da imagem),
então quem volta à rede é o apt e o npm.

Commit: `chore: unifica a base das imagens e fixa a versão do uv`.


---

## Avaliação de modelo e de contexto (pedido pelo usuário)

> **Escrita no planejamento, revista em 2026-09-06.** As etapas 1–7 citadas
> abaixo já foram executadas, com Opus. A revisão mediu o custo real: os
> documentos somam ~12 mil tokens e o projeto inteiro ~29 mil, de modo que
> recomeçar uma sessão é barato — e é o que evita pagar um contexto grande em
> cada requisição. O gasto vem do tamanho da sessão, não do tamanho dos
> documentos. A recomendação de modelo por tipo de tarefa continua valendo:
> Opus onde há decisão de arquitetura (8.2), Sonnet no trabalho mecânico
> (8.1 e 9).


**Modelo.** Depois deste planejamento, o projeto não pede mais Opus. As etapas 1–7
são código de padrão bem estabelecido: uma dataclass com validações, um
`random.sample`, desenho em `reportlab.canvas`, duas rotas FastAPI e um formulário
Bootstrap. **Recomendo trocar para Sonnet 5** na execução — ele cobre isso com
folga e a diferença de custo é significativa ao longo de 7 etapas com commits.
Vale voltar a Opus apenas se aparecer uma decisão de arquitetura nova (por
exemplo, quando você for de fato colocar o serviço online, ou se o layout do PDF
exigir cálculos de tipografia mais delicados do que o previsto).

**Contexto e subagentes.** O projeto inteiro — código, testes, HTML/JS — deve
ficar em torno de 1.500–2.500 linhas. Isso cabe com muita folga na janela de
contexto, então **não há necessidade de delegar para subagentes**. Delegação aqui
seria contraproducente: cada subagente começa sem contexto e precisa re-derivar as
decisões acima, custando mais do que economiza. O mecanismo que já protege o
contexto neste plano é outro: os commits por etapa e os três checkpoints de
avaliação funcionam como pontos de retomada — se a sessão precisar recomeçar,
basta o estado do repositório mais os arquivos de plano e de decisões.

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

A maior parte trata de código já escrito, mas nem tudo: a seção **Decisões de
publicação** registra escolhas fechadas *antes* da execução das etapas 8 e 9.
Elas estão aqui, e não no `PLANO.md`, porque o que se quer guardar é a
alternativa descartada — e uma alternativa descartada no plano se parece com uma
questão ainda em aberto.

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

## Etapa 6.3 — Teto do universo — **concluída**

`numero_elementos` é o **tamanho do universo sorteável**, o mesmo conceito que
`len(palavras)`: em `models.py` o universo de tipo `numeros` é
`1..numero_elementos` e o de palavras é a própria lista. Tinham tetos
diferentes — `le=10_000` no schema para os números e nenhum para as palavras.

**Uma constante só, `MAX_ELEMENTOS = 100` em `models.py`**, valendo para os
dois. Dez mil era alto demais para um bingo impresso e era um vetor de consumo:
`universo` materializa a tupla e `combinacoes_possiveis` roda `math.comb` sobre
ela.

| Entrada | Antes | Agora |
|---|---|---|
| `numero_elementos` | `le=10_000` no schema, `>= 1` em `models.py` | 1 a 100, nos dois |
| Quantidade de palavras | sem limite | `max_length=100` no schema e regra em `models.py` |

Alterado no mesmo trio da armadilha do `MAX_FOLHAS` — `models.py` (a
autoridade), `api.py`, `static/app.js` e o `max` do campo em `index.html`. O
`app.js` **não tinha teto superior algum** para o universo; agora tem, com a
mesma mensagem do backend. O literal `100` da checagem de células virou
`MAX_CELULAS`, que é a mesma duplicação sem nome.

**Consequência aceita, decidida com ela à vista:** a validação exige universo
*estritamente maior* que os elementos por folha. Com o universo em 100 e
`MAX_CELULAS` em 100, uma grade de exatamente 100 células (10×10, 5×20, 20×5 —
todas de lados pares, portanto sem centro livre) passa a ser impossível, porque
exigiria 101 elementos. Grades de até 99 células seguem funcionando. Se um dia o
10×10 fizer falta, o teto vira 101.

Conferido caso a caso que as mensagens do `app.js` e as de `models.py` coincidem
nos dois tipos, no teto, no teto + 1 e nas grades de 99, 100 e 121 células.

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


## Etapa 8.1 — Integração contínua — **concluída**

### Dois workflows, e o motivo é permissão

`ci.yml` e, depois, `deploy.yml` — separados porque o deploy precisa de
`id-token: write` para o Workload Identity Federation. Num arquivo só, a
permissão mais alta alcançaria os jobs que executam código de pull request. O
`ci.yml` roda com `contents: read` e nada mais. A separação também mantém o CI
verde ou vermelho independente de uma falha de infraestrutura do deploy.

### Três jobs paralelos

| Job | O que cobre |
|---|---|
| `testes` | `uv lock --check`, `uv sync --frozen`, `uv run pytest -q` |
| `estatica` | `ruff check`, `ruff format --check`, `node --check static/app.js` |
| `imagem` | constrói o estágio `producao`, sobe o container e roda o teste de fumaça |

Independentes e em paralelo: um lint quebrado e um teste quebrado se distinguem
de relance, sem ler registro.

**Sem matriz de versões do Python.** O `requires-python` é `>=3.14` e a imagem é
`python:3.14-slim-bookworm`. Testar em 3.12 validaria um ambiente que nunca vai
existir.

**O `uv lock --check` automatiza uma convenção humana.** O trabalho acontece em
duas máquinas, e a regra "quem alterar dependências commita o `uv.lock` junto"
dependia de lembrar. Agora falha o CI.

**O `node --check static/app.js`** é a única verificação automática que o
frontend tem. Um erro de sintaxe no `app.js` hoje só apareceria ao abrir a
página com o cache limpo — e o cache dos estáticos é uma armadilha já conhecida.

### Construir não prova que funciona: o teste de fumaça

O plano previa só construir a imagem sem publicar. Isso não teria pego nenhuma
das armadilhas já registradas — `RAIZ_PROJETO` calculada a partir do
arquivo-fonte, `static/` que não viaja num wheel, venv não-relocável entre
bases. **Todas passam pelo build e quebram na primeira requisição.**

Por isso o job sobe o container e roda `scripts/fumaca.sh`, que confere a página
inicial, os dois estáticos (`app.js` e o logo), o `POST /api/preview` e o
`POST /api/jogo`. As duas últimas usam centro livre, então também provam que o
logo padrão chegou na imagem e que o reportlab consegue abri-lo.

O script mora em `scripts/`, e não embutido no YAML, para poder rodar localmente
contra um `uvicorn`: foi assim que ele foi validado, inclusive no caminho de
falha, num ambiente sem Docker. Na Etapa 8.2 ele valida de graça a mudança do
`PORT` no `CMD`.

### Ruff, e a formatação que veio junto

Não havia linter. O `charliermarsh.ruff` já estava declarado no
`devcontainer.json`, mas o binário nunca fora instalado — a extensão apontava
para o vazio. Entrou como dependência de desenvolvimento, com
`select = ["E", "F", "I"]`: erros de sintaxe e de fluxo, mais imports ordenados.
Nada de estilo além do que o `ruff format` já resolve.

Custou um passe de formatação em 6 arquivos e 8 correções (7 linhas longas e um
import não usado nos testes). O `ruff.path` no devcontainer aponta para
`/opt/venv/bin/ruff`, para que o editor use a mesma versão do `uv.lock` e do CI,
e não a que a extensão embute.

### Versões das actions

`actions/checkout@v7`, `astral-sh/setup-uv@v10.0.1`,
`docker/setup-buildx-action@v4` e `docker/build-push-action@v7`.

**O setup-uv é o fora da curva, e derrubou a primeira execução.** Ele parou de
publicar as tags móveis de major depois da v7: `tags/v10` dá 404, só existem
versões completas. Escrito como `@v10`, o job morre no "Set up job", antes de
qualquer passo próprio. Conferir a tag pela API (`/git/ref/tags/<tag>`) é mais
confiável do que ler a página de releases, que foi como o erro entrou.

A versão do uv fica em `env.UV_VERSION`, espelhando o `ARG UV_VERSION` do
`Dockerfile` — as duas mudam juntas, senão o CI resolve dependências com uma
ferramenta diferente da que constrói a imagem.

### O primeiro CI foi vermelho, e o segundo motivo era o próprio teste

Além da tag inexistente, o `scripts/fumaca.sh` reprovava por defeito próprio:
`curl | head -c 4` sob `set -o pipefail`. O `head` fecha o cano depois dos
primeiros bytes, o curl morre de EPIPE e o pipeline falha — **mas só quando a
resposta não cabe no buffer de 64 KB do pipe**, o que faz da reprovação uma
corrida. Com o PDF de 48 KB, passou na primeira execução local e falhou nas
seguintes com o mesmo comando.

O script deixou de ter pipe a partir do curl: cada resposta vai para um arquivo
e é conferida de lá — código HTTP, assinatura e tamanho, cada falha com sua
mensagem. Validado em 10 execuções seguidas, contra porta morta e contra um
servidor que responde 200 com texto no lugar do PDF.

Execução verde: `testes` 12s, `estatica` 12s, `imagem` 22s — os 22s incluem
construir o estágio `producao`, subir o container e a fumaça.

## Decisões de publicação — tomadas antes da execução

Fechadas em 2026-09-06, a partir de um briefing produzido numa sessão paralela e
conferido contra o código. As etapas 8 e 9 ainda não foram executadas, mas as
escolhas já estão feitas: ficam aqui para não serem reabertas como se fossem
questões em aberto no `PLANO.md`.

### Hospedagem: Google Cloud Run

| Opção | Por que não |
|---|---|
| Hugging Face Spaces | Sem cartão e o mais fácil de publicar, mas lido como vitrine de demonstração; perde valor como peça de portfólio |
| Render | Dorme em ~15 min e acorda em dezenas de segundos — péssimo para quem abre o link uma vez por mês |
| Azure Container Apps | Equivalente ao Cloud Run, sem vantagem que justifique a troca |
| Fly.io | Modelo gratuito mudou ao longo dos anos; incerto |
| Oracle Always Free | Sempre ligada, mas exige administrar TLS, firewall e atualizações |

Pesou também um critério não técnico: o projeto serve de **portfólio**, e o Cloud
Run comunica competência de operação que uma plataforma de demonstração não
comunica. O diferencial, porém, não é a plataforma e sim o que existe em volta —
CI, salvaguardas de custo e o registro das decisões.

### Servidor: uvicorn sozinho, um único worker

A objeção habitual de "não exponha uvicorn direto à internet" **não se aplica no
Cloud Run**: o Google Front End fica na frente do contêiner e faz o que o nginx
faria — termina o TLS, trata HTTP/1.1 e HTTP/2, normaliza e bufferiza as
requisições, absorve ataque de cliente lento e aplica limites. O contêiner só
recebe HTTP simples de um proxy confiável. É por isso que **nginx está
descartado**: ele não substitui o uvicorn (não executa Python), seria um proxy a
mais na frente dele, e só voltaria a fazer sentido numa VPS administrada por nós.

| Alternativa | Por que não |
|---|---|
| Gunicorn + UvicornWorker | Supervisão redundante: o Cloud Run já reinicia contêiner não saudável. Custa um processo e ~30-50 MB |
| Hypercorn | Só compensa pela cobertura de protocolos (HTTP/3, Trio); mais lento e comunidade menor |
| Granian | Bom desempenho e menos memória, mas projeto jovem e ecossistema menor |
| Daphne | Mais lento; sem motivo fora de Django Channels |
| Waitress / uWSGI | Só fazem sentido em WSGI; o uWSGI está em modo manutenção |

**Um worker só**, porque o Cloud Run escala criando instâncias, não fazendo fork
de workers: vários apenas multiplicariam a memória por instância. No volume
previsto — cerca de uma requisição por hora — o servidor é irrelevante para
desempenho.

### Sem banco de dados, e sem estado no servidor

O sistema de arquivos do contêiner no Cloud Run é **tmpfs**: o que se escreve
conta como memória da instância e desaparece quando ela é reciclada — o que
acontece após ~15 min de ociosidade, a cada deploy e a critério do Google. Uma
segunda instância nasce com uma cópia vazia. **SQLite dentro do contêiner perde
dados silenciosamente.**

Montar um bucket por Cloud Storage FUSE foi avaliado e **corrompe SQLite**: o
FUSE não oferece lock de arquivo para escrita concorrente, o último a escrever
vence, e não é um sistema de arquivos POSIX completo — e o SQLite depende de
locks POSIX.

Alternativas viáveis, caso um dia houvesse estado no servidor: SQLite +
Litestream com `max-instances=1`, Firestore (cabe na camada gratuita neste
volume), Cloud SQL Postgres (~US$ 10 a 25/mês) ou Postgres gerenciado externo.
**Nenhuma é necessária**, e a ausência de estado tem um efeito que vale tanto
quanto funcionalidade: não há dado pessoal no servidor, nada para vazar, nada
para fazer backup e nenhuma exposição à LGPD.

### Estado no computador do professor: arquivo, não cookie

**Cookies descartados:** 4 KB por cookie, e trafegam em toda requisição. Uma
lista de palavras mais um logo estoura isso de imediato.

O arquivo JSON exportável (Etapa 9) vence o `localStorage` em durabilidade —
sobrevive a limpeza de navegador, troca de máquina e reimagem de laboratório
pela TI da escola — e em compartilhamento: o professor manda a configuração por
e-mail para um colega, o que vira um recurso sem custo de código. A desvantagem
é ser manual, e alguém vai perder um arquivo. O `localStorage` **continua** como
conveniência; o arquivo é o caminho durável.

### Imagem: construir uma vez e promover pelo digest

Decidido na 8.1, executado na 8.2. As duas formas consideradas:

- **Reconstruir no deploy** — mais simples, sem credencial no CI, mas o que foi
  testado não é literalmente o que é implantado.
- **Construir uma vez e promover** — o CI empurra a imagem com a tag do SHA e o
  deploy aponta o Cloud Run para o **digest**.

Escolhida a segunda. Implanta-se o binário exato que passou nos testes, e o
rollback vira apontar para o digest anterior. O digest, e não a tag, porque uma
tag pode ser reescrita. O preço é credencial de publicação já no CI e uma
política de limpeza no Artifact Registry, que acumula uma imagem por commit.

Foi por isso que o job `imagem` já nasceu etiquetando com `${{ github.sha }}`:
falta só a autenticação e o `push`.

### Autenticação: serviço aberto, protegido por limites

Decisão do usuário, com as alternativas à vista:

| Opção | Por que não |
|---|---|
| Senha compartilhada | Os professores usam o sistema 4 a 6 vezes por ano e vão esquecê-la — gerando exatamente o chamado de suporte que se quer evitar |
| IAM do Cloud Run | Exige conta Google por professor e um proxy autenticador (IAP) para funcionar no navegador; muito setup para "publicar e não mexer por um ano" |

A proteção vem então de limites, não de identidade: teto do corpo da requisição
(6.2), teto do universo (6.3), limite de taxa por IP (8.3), `--max-instances 3`
e alerta de orçamento (8.2). **O teto de instâncias é o que limita a exposição
financeira**, que é o risco real de deixar o serviço no ar e esquecê-lo — mais
do que o abuso em si.

---

## Etapa 8.2 — Publicação no Cloud Run — **concluída**

O serviço está no ar em
`https://bingo-286308093839.southamerica-east1.run.app`, publicado pelo
`deploy.yml` a cada push em `main`, sem nenhuma chave guardada em lugar algum.

### A porta vem da variável `PORT`, e o `exec` preserva o PID 1

O Cloud Run injeta `PORT=8080` no contêiner e ignora o `EXPOSE`, enquanto o
`CMD` fixava 8000: o serviço subiria numa porta que ninguém procura e o deploy
nunca ficaria pronto. Como a forma exec do `CMD` não expande variáveis, ele
passou à forma shell.

O `exec` não é enfeite: sem ele o `sh` continua sendo o PID 1, recebe o
`SIGTERM` do encerramento e não o repassa — cada instância derrubada esperaria
o tempo limite antes de morrer à força. Com ele, o uvicorn substitui o shell no
mesmo processo e recebe o sinal direto.

O `HEALTHCHECK` tinha a mesma porta fixa e não pode discordar do `CMD`. Ele
continua na forma exec e lê a variável **em Python**
(`os.environ.get('PORT', '8000')`), o que evita trazer um shell só para
expandir. O Cloud Run o ignora, mas ele vale localmente e no job `imagem` do CI.
O `EXPOSE 8000` ficou como documentação da porta padrão.

### `--proxy-headers`, que deixou de ser opcional

Atrás do Google Front End, todo pedido chega ao contêiner com o IP do proxy. Sem
`--proxy-headers --forwarded-allow-ips='*'`, o limite de taxa por IP da Etapa
8.3 veria o tráfego inteiro como um cliente só — isto é, não funcionaria.
Confiar em qualquer proxy é aceitável exatamente porque o contêiner não recebe
tráfego de mais ninguém; a mesma premissa que descarta o nginx.

### Como foi verificado

O devcontainer não tem Docker, então a primeira conferência foi feita sobre os
comandos e não sobre a imagem: a expansão do `CMD` dá 8000 sem `PORT` e 8080 com
`PORT=8080`; o `exec` preserva o PID; o `'*'` chega como argumento único, sem
expansão de glob; e o `X-Forwarded-For` de teste aparece no log de acesso no
lugar do IP local.

Isso não substituiu construir a imagem — as armadilhas do `RAIZ_PROJETO`, do
`static/` e do venv não-relocável passam pelo build e só quebram na primeira
requisição. Quem fechou esse buraco foi o CI, e o job `imagem` passou a subir o
contêiner **nas duas portas**: `PORT=8080`, que é o que o Cloud Run injeta, e o
padrão de 8000, que é o que vale no `docker run` local. A expansão é uma linha
de shell — falha inteira ou não falha —, mas descobrir isso no primeiro deploy
seria caro, e o custo de cobrir é um `docker run` a mais.

### O `push` não coube no `ci.yml`, e o motivo é o mesmo de sempre

O plano previa que o job `imagem` do `ci.yml` ganhasse autenticação e `push`.
Não dá: aquele workflow roda em pull request, e dar-lhe `id-token: write`
entregaria credencial do projeto no Google a código de terceiros. A sequência
inteira — construir, testar a fumaça, empurrar, implantar — foi para o
`deploy.yml`, disparado só em push para `main`.

Isso preserva a decisão de construir uma vez e promover: a imagem sai da máquina
só depois de passar no teste, e o deploy aponta para o **digest lido de volta
do registro** com `docker image inspect`, não para a tag. O `ci.yml` continua sem credencial nenhuma, validando PRs.

O job se pula sozinho enquanto `vars.GCP_WIF_PROVIDER` estiver vazia. Sem isso,
todo push em `main` teria ficado vermelho durante os dias entre escrever o
workflow e terminar a configuração do Google.

### Duas contas de serviço, e uma delas sem papel nenhum

A `github-deploy` publica e implanta (`artifactregistry.writer`, `run.admin`, e
`iam.serviceAccountUser` sobre a outra). A `bingo-runtime` é a identidade que o
contêiner veste ao rodar e **não tem papel algum**, de propósito: o serviço é
stateless e não chama nada do Google. Sem ela o Cloud Run usaria a conta padrão
do Compute Engine, que costuma vir com poder de Editor sobre o projeto inteiro —
poder de sobra para uma rota pública sem autenticação.

Nenhuma chave JSON foi criada. O GitHub apresenta um token OIDC de curta duração
e o Google o troca por credencial temporária; quem autoriza é a condição
`assertion.repository == 'aureliobarbosa/bingo'` no provedor. Sem essa condição,
qualquer repositório do GitHub no mundo poderia fazer a mesma troca.

### A configuração do Google virou script

`scripts/configura-gcp.sh` faz os doze comandos do `gcloud` na ordem certa e
imprime, ao final, as quatro Variables a cadastrar no GitHub. Existe porque
ninguém repete isso de memória daqui a um ano, e porque um projeto recriado
precisa sair igual. Roda no Cloud Shell, sem instalar nada. Os `create` toleram
recurso já existente; qualquer outro erro aborta.

O `gcloud` **não entra na imagem**: ela é o artefato implantado, e uma
ferramenta de administração da nuvem dentro de um serviço público é poder que
ele nunca precisa ter. É o mesmo raciocínio da conta sem papéis.

### O que a execução mediu

| Medida | Valor |
|---|---|
| Partida a frio, após 17 min ocioso | 2,56 s |
| Requisição com a instância quente | 0,25 s |
| Gerar 100 folhas pela rede | 0,67 s, 160 KB, 100 páginas |

A partida a frio de 2,56 s ficou perto dos 2,8 s medidos no contêiner local, o
que indica que o tempo é quase todo do processo subindo — Python, FastAPI e
reportlab carregando — e não da infraestrutura alocando instância. No uso
previsto o professor pega a partida a frio quase sempre, e 2,5 s até a página
aparecer é aceitável; foi exatamente o que descartou o Render, que dorme e
acorda em dezenas de segundos.

Um aviso apareceu no primeiro deploy: o `docker/login-action@v3` tem como alvo o
Node.js 20, descontinuado nos runners. Subiu para `v4`, que declara `node24`.
Vale a armadilha já registrada — a tag foi conferida pela API antes de ser
escrita no workflow.

---

## Etapa 8.3 — Limite de taxa, cache e cabeçalhos — **concluída**

Os três itens fecham a lista de proteções que substituem a autenticação, pela
decisão registrada em "Autenticação: serviço aberto, protegido por limites".

### Limite de taxa: janela deslizante em memória, e o que ela não faz

Um dicionário de IP para as marcas de tempo (`time.monotonic`) das requisições
dentro de uma janela de 60 segundos, em `src/bingo/api.py`. Biblioteca padrão,
como o resto do backend: uma dependência de limite de taxa traria Redis junto,
e Redis para dez usuários por ano seria mais infraestrutura para esquecer no ar
do que o próprio serviço.

Não há cadeado, e não por descuido: toda a contabilidade roda dentro do
middleware `async`, sem `await` no meio, então duas requisições nunca a
executam ao mesmo tempo — o laço de eventos é um só. As rotas é que rodam em
threads, e elas não tocam no dicionário.

O dicionário é varrido uma vez por janela, soltando os IPs que não voltaram.
Sem isso, um varredor de portas trocando de IP faria a memória crescer sem fim.

**O teto é 120 por minuto**, generoso de propósito. O preview tem debounce de
400 ms, o que põe o pior caso teórico de um humano em torno de 150 por minuto e
o caso real bem abaixo; um bot em laço passa de 120 em segundos. A régua é
essa: separar o professor do laço, não medir educadamente o professor.

**O limite só alcança `/api/`.** Uma visita normal já pede três estáticos, e
contá-los gastaria a cota de quem não fez nada de errado. O custo real está em
gerar PDF. Quem estoura a cota continua conseguindo abrir a página — há teste
para isso.

**A limitação, dita por inteiro:** cada instância tem o seu próprio dicionário.
Com `--max-instances 3` o teto efetivo é até 3x o configurado, e ele zera
quando a instância recicla. Isso contém bot em laço; não contém atacante
determinado, que exigiria armazenamento compartilhado. Quem limita a exposição
financeira continua sendo o `--max-instances 3`, não este contador.

O `--proxy-headers` do `Dockerfile`, decidido na 8.2, é o que faz o contador
enxergar o IP do cliente em vez do Google Front End. As duas coisas caem
juntas: sem ele, este limite veria o tráfego inteiro como um cliente só.

### Cache dos estáticos: `no-cache`, que é revalidar e não desistir

`StaticFiles` não manda `Cache-Control` nenhum, então a heurística do navegador
decidia — e depois de uma edição no `app.js` ele podia seguir rodando a versão
velha. A armadilha estava registrada no `CLAUDE.md` porque já custou
diagnósticos errados.

A subclasse `EstaticosRevalidados` manda `Cache-Control: no-cache`, que não é
"não guarde" e sim "guarde, mas pergunte antes de usar". O `ETag` que o
`FileResponse` já monta faz a pergunta caber num 304 sem corpo; há teste que
confere o 304 e o cabeçalho nele. A rota `/` leva o mesmo cabeçalho — sem 304,
porque conferir `If-None-Match` à mão não paga por um `index.html` de poucos KB.

A alternativa era versão na URL (`app.js?v=hash`), que permite cache eterno mas
pede o build step que o projeto não tem. Com uma dezena de usuários por ano,
revalidar não custa nada e o build step custaria muito.

### Cabeçalhos de segurança, e a CSP que coube apertada

Middleware mais externo — declarado por último, que é onde o Starlette põe o de
fora —, então as respostas 413 e 429 dos middlewares de dentro também saem com
os cabeçalhos. A ordem foi conferida antes de escrever o código, não suposta.

A política de conteúdo pôde dispensar `unsafe-inline` porque a página não tem
script embutido, nem atributo `style=`, nem `innerHTML` em lugar nenhum. As duas
únicas liberações são as que a página de fato usa, e cada uma tem teste:

- **`https://cdn.jsdelivr.net` em `style-src`** — de onde vem o CSS do
  Bootstrap. Conferido: os 23 `url()` desse arquivo são todos `data:`, nenhum
  recurso externo. Por isso `img-src 'self' data:`.
- **`blob:` em `frame-src` e `object-src`** — o PDF do preview chega pelo
  `fetch`, vira URL de blob e é desenhado num `<iframe>`. Vai nas duas
  diretivas porque ambas já foram o caminho de desenhar PDF embutido em algum
  navegador, e o preço de errar é o preview em branco.

**Sem `Strict-Transport-Security`**: o cabeçalho é ignorado fora do HTTPS e o
domínio `run.app` já vem na lista de pré-carga dos navegadores. CORS segue
desnecessário — frontend e API são a mesma origem.

### Como foi verificado

Os 70 testes e o `ruff` cobrem o que é determinístico: os cabeçalhos em cada
tipo de resposta, o 304 da revalidação, a janela deslizante e o 429.

O limite de taxa foi exercitado contra um `uvicorn` de verdade, não só pelo
`TestClient`, porque é lá que o middleware roda no laço de eventos com
requisições separadas: 125 chamadas seguidas a `/api/preview` deram **120
respostas 200 e 5 respostas 429**, com `Retry-After: 58`. O contador conta o
que promete.

A CSP não tem como ser testada daqui — quem obedece a ela é o navegador, e não
há nenhum instalado neste ambiente. Quem conferiu foi o usuário, no Firefox, e
o jeito de ler o resultado vale registrar:

**A ausência de erro é prova fraca; o aviso do pdf.js é prova forte.** O console
não trouxe nenhuma linha de `Content-Security-Policy`, mas trouxe um aviso do
próprio pdf.js sobre a URL do blob (`Invalid absolute docBaseUrl:
"blob:http://localhost:8000/..."`, que é ele tentando usar o blob como base
para links relativos que os nossos PDFs não têm). Esse aviso só pode existir se
o visualizador **abriu** o blob — ou seja, é o `frame-src blob:` funcionando,
dito pelo lado de dentro. Console silencioso poderia ser CSP correta ou preview
que nem foi tentado; o aviso distingue os dois casos.

O Firefox é o teste severo dos dois navegadores: o pdf.js é uma página comum,
sujeita à CSP da página que o criou. O Chrome desenha PDF por um visualizador
interno, que não passa pelas mesmas diretivas — passar nele diria menos.

### O timeout de geração já existe, e um em processo seria teatro

O plano pedia "timeout de geração". Ele já está no `deploy.yml`, como
`--timeout=60s`: o Cloud Run corta a requisição de fora, que é o único lugar de
onde dá para cortar.

Um timeout dentro do processo foi medido antes de ser descartado. As rotas são
`def` síncronas, que o Starlette executa numa thread do pool; `asyncio.wait_for`
em volta cancela a *tarefa*, mas a thread não é interrompível e o
`anyio.to_thread.run_sync` só devolve quando ela termina. Num teste com timeout
de 0,5 s sobre um trabalho de 3 s, a resposta 504 saiu em **3,01 s** — o cliente
recebe outro código, o servidor gasta exatamente o mesmo. Seria trocar o rótulo
da resposta, não liberar recurso nenhum.

O que de fato limita o trabalho é a entrada, que já é limitada: no máximo 100
elementos e 100 folhas, medidos em 0,67 s pela rede no pior caso.

---

## Etapa 8.4 — Um endereço que dá para ditar

`bingo-286308093839.southamerica-east1.run.app` funciona, mas ninguém dita isso
para um professor no corredor. A pergunta que abriu a etapa foi se o Google dá
um domínio de graça.

### Não existe domínio grátis do Google, mas existe subdomínio

O Google Domains foi vendido à Squarespace em 2023; o **Cloud Domains** que
sobrou é registrador pago, ~US$ 12/ano num `.com`. Registro de domínio grátis
não há.

O **Firebase Hosting**, porém, dá `<nome>.web.app` sem custo, com HTTPS,
certificado gerenciado e CDN — e aceita *rewrite* para um serviço do Cloud Run.
É o mais perto de "domínio grátis do Google" que existe, e é a opção que a
própria documentação do Cloud Run recomenda como a de baixo custo.

### Por que não o domain mapping nativo do Cloud Run

Ele existe e seria o caminho óbvio, mas **continua em preview e só vale em dez
regiões** — `asia-east1`, `europe-west1`, `us-central1` e afins. A nossa,
`southamerica-east1`, não está na lista. Usá-lo exigiria mudar o serviço de
região, o que piora a latência de quem vai usar (professores no Brasil) e ainda
adota uma feature que o próprio Google marca como não pronta para produção.

O balanceador de carga externo global resolveria tudo e dá controle total, mas
a regra de encaminhamento custa ~US$ 18/mês, para um serviço que atende três
requisições por dia. Cloudflare de graça na frente também não serve direto: o
`run.app` roteia pelo cabeçalho `Host`, então exigiria um Worker reescrevendo-o
— mais peça móvel do que o problema merece.

### O `public` fica vazio de propósito

O `firebase.json` exige a chave `public` mesmo sem estático nenhum, e o rewrite
`**` manda toda requisição ao Cloud Run. A tentação é copiar `static/` para
dentro do `public` e deixar a CDN servir — e é armadilha: **o Hosting resolve
arquivo estático antes de aplicar o rewrite**, então a cópia passaria por cima
do que o serviço entrega e as duas divergiriam no primeiro `app.js` alterado.
O `RAIZ_PROJETO` continua sendo a única fonte, com o `no-cache` e o ETag da
Etapa 8.3 valendo como antes. A CDN não guarda nada por conta própria: ela só
cacheia resposta com `Cache-Control` público, e o PDF é `POST`.

### O IP do cliente muda de cabeçalho atrás da CDN

Essa é a única consequência que exigiu código. Pelo `run.app` direto, o
`--proxy-headers` da Etapa 8.2 faz o `request.client` já ser o visitante. Atrás
do Hosting, não: quem fala com o Cloud Run é a CDN (Fastly), e o IP real vem em
**`Fastly-Client-Ip`**. Sem lê-lo, o limite de taxa da 8.3 deixaria de contar
por cliente e viraria um teto global — um usuário sozinho gastaria a cota de
todos. `_cliente()` passa a preferir o cabeçalho e só cai para o
`request.client` quando ele falta.

O cabeçalho é forjável por quem chame o `run.app` direto. Não é porta nova: é a
mesma exposição que o `--forwarded-allow-ips='*'` já aceitou com o
`X-Forwarded-For`, e a régua continua sendo conter bot em laço.

### O `run.app` continua público, e o deploy do Hosting é manual

O Hosting é uma porta a mais, não um muro: o endereço antigo segue respondendo.
Fechá-lo exigiria ingress interno mais balanceador — exatamente o custo recusado
acima.

O `firebase.json` aponta para o *serviço*, não para uma versão dele, então nada
nele muda a cada push: uma publicação só, à mão, e o `deploy.yml` continua sem
papel novo no WIF. Automatizá-lo custaria um papel de Firebase Hosting Admin na
conta de deploy para algo que praticamente não muda.

### O 403 do `addfirebase` era aceitação de termos, não permissão

Ligar o Firebase num projeto do Cloud que já existe custou mais que o resto da
etapa, e o diagnóstico vale registrado porque a mensagem do Google engana:
`projects:addfirebase` devolveu **403 "The caller does not have permission"** em
todas as tentativas. A conta era `roles/owner` na política do projeto, conferido
por `getIamPolicy`, e nada disso era o problema.

A eliminação, na ordem em que foi feita:

1. **API desligada** — `firebase.googleapis.com` e `firebasehosting.googleapis.com`
   estavam `DISABLED`. Isso de fato produz 403 com essa mesma mensagem, mas
   ligá-las não resolveu.
2. **IAM** — `testIamPermissions` devolveu `firebase.projects.update` concedida,
   e `getIamPolicy` mostrou `roles/owner`. Descartado.
3. **Organização ou pasta com política** — `getAncestry` mostrou o projeto sem
   pai nenhum. Descartado.
4. **Projeto de cota** — repetir a chamada com `x-goog-user-project` não mudou
   nada. Descartado.

O que sobrou, e era: **a conta nunca tinha usado o Firebase e não aceitara os
termos de serviço**, que só existem na interface. O sinal que apontou para lá:
`GET /v1beta1/availableProjects` respondia **200 listando o projeto** enquanto o
`POST :addFirebase` dava 403 — leitura liberada e escrita negada com Owner
comprovado não é IAM, é gate de conta. E o console do Firebase não listava o
projeto para importar justamente porque é esse endpoint que alimenta a lista.

A saída foi criar um projeto qualquer pelo console (o fluxo de criação apresenta
os termos), e então o `addfirebase` no projeto de verdade passou na primeira
tentativa. O projeto criado só para aceitar termos pode ser apagado.

**Se isto reaparecer noutro projeto**: não procure papel faltando. Compare
`availableProjects` com `addFirebase`; se um responde e o outro não, é termo, e
o caminho é o console.

### Como foi verificado, e o que a CDN não estragou

`scripts/fumaca.sh https://bingo410.web.app` passou nos quatro testes pelo
endereço publicado — página, estáticos, preview e jogo completo, com PDF de
verdade nos dois últimos (47 KB e 49 KB). O mesmo script que roda no CI contra o
container serve aqui sem uma linha de mudança, que era a ideia dele desde a 8.2.

Os cabeçalhos foram conferidos no endereço novo, porque um proxy no meio é
exatamente o lugar onde eles se perdem: CSP, `nosniff`, `X-Frame-Options`,
`Referrer-Policy` e `Permissions-Policy` chegam **inteiros**, e o `no-cache` com
ETag dos estáticos também. A CDN não reescreveu nada e não guardou nada por
conta própria.

Falta a conferência da CSP no Firefox pelo endereço novo. A da 8.3 vale como
indício forte — mesma origem, mesmo `blob:` —, mas quem obedece à CSP é o
navegador, e o erro é silencioso.

### Sem HSTS, pelo mesmo motivo de antes

`web.app`, como `run.app`, já vem na lista de pré-carga dos navegadores, então
`Strict-Transport-Security` continua ausente do serviço sem prejuízo — e a
medição do endereço publicado mostrou mais: **o próprio Hosting carimba o
cabeçalho** (`max-age=31556926; includeSubDomains; preload`), sem ninguém pedir.
Pelo `run.app` direto ele não vem, e continua não fazendo falta pelo mesmo
motivo de sempre. **O gatilho para
acrescentá-lo é registrar um domínio próprio** (`.com.br`, `.com`): aí o
cabeçalho passa a valer de verdade. Se esse dia chegar, os preços de custo
levantados aqui foram R$ 40/ano no Registro.br para `.com.br` e ~US$ 9,77/ano na
Cloudflare Registrar para `.com`; o domínio aponta para o mesmo Firebase
Hosting, com verificação por TXT e registros A, sem refazer nada do que está
acima.

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

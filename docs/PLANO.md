# Sistema de Bingo via Web — Plano de Implementação

> **Andamento** — Etapas 0 a 6 concluídas (backend, PDF, API, interface e conexão),
> mais o logo na célula central. Pendentes: 6.1 (refinamentos), 7 (container),
> 8 (servidor, nuvem e segurança) e 9 (documentação).

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
- `1 ≤ numero_folhas ≤ 500` — teto de proteção para o serviço online
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

### 6.1.4 Botão "Restaurar padrões"

Os parâmetros ficam no `localStorage` do navegador (`bingo.configuracao`), e hoje só
dá para voltar aos valores padrão pelo console do navegador — inaceitável para um
serviço público. Um botão no painel limpa a chave e recarrega o formulário. A
preferência de tema (`bingo.tema`) fica de fora, por ser configuração de exibição e
não do jogo.

Arquivo: `static/app.js` e `static/index.html`.

Commit por item, como nas demais etapas.

**Parar aqui e pedir avaliação do usuário.**

## Etapa 7 — Container

Empacotar o serviço em uma imagem, que é o artefato que as etapas seguintes
publicam.

- `Dockerfile` com `uv` para instalar as dependências, executando como usuário sem
  privilégios e expondo `uvicorn`.
- Incluir o diretório `static/` na imagem: hoje `RAIZ_PROJETO` é calculada a partir
  do arquivo-fonte (`src/bingo/pdf.py`, `parents[2]`), então a imagem precisa copiar
  a árvore do projeto — instalar apenas o wheel deixaria `static/` e o logo de fora.
  Alternativa a avaliar aqui: mover `static/` para dentro do pacote.
- `.dockerignore`, build reproduzível a partir do `uv.lock`.
- Verificação: subir o container localmente, gerar um PDF e conferir as páginas.

Commit: `chore: empacota o serviço em container`.

## Etapa 8 — Servidor web, nuvem e segurança

Decisões de operação, todas ainda em aberto:

- **Servidor**: `uvicorn` sozinho ou atrás de um proxy reverso (nginx, Caddy,
  Traefik); número de workers; timeouts.
- **Nuvem**: escolher o destino (VPS, Fly.io, Render, Cloud Run…) pesando custo,
  facilidade e limites de CPU — a geração de PDF é trabalho de CPU, não de I/O.
- **Segurança**, vinculada às escolhas acima:
  - TLS e redirecionamento de HTTP para HTTPS;
  - limite de taxa por IP: gerar 500 folhas é caro, e a rota é aberta e sem
    autenticação — é o vetor de abuso mais óbvio do serviço;
  - limite de tamanho do corpo da requisição (lista de palavras e, se a Etapa 6.1.3
    ficar pronta, a imagem enviada);
  - validação estrita da imagem enviada, se houver upload;
  - cabeçalhos de segurança e política de CORS (hoje desnecessária, porque
    frontend e API são a mesma origem);
  - teto de trabalho por requisição (`MAX_FOLHAS`, `MAX_CELULAS` já existem em
    `src/bingo/models.py`) e timeout de geração.

Commit: `chore: configuração de servidor e implantação`.

## Etapa 9 — Documentação

Escrita depois que o container e o servidor estiverem definidos, para descrever o
que de fato existe.

`README.md` com: o que é, como rodar localmente
(`uv run uvicorn bingo.api:app --reload`), como rodar os testes (`uv run pytest`),
como construir e executar o container, e como está implantado.

Commit: `docs: README com instruções de uso e deploy`.

---

## Verificação

```bash
uv run pytest -q                                    # todos os testes
uv run uvicorn bingo.api:app --reload               # servidor local
```

Depois, no navegador em `http://127.0.0.1:8000`:
1. Números, 1..75, grade 5×5 com centro livre, 10 folhas → preview mostra 24
   números + centro vazio.
2. Palavras (colar 30 palavras), grade 4×4, 5 folhas → preview mostra 16 palavras,
   nenhuma estourando a célula.
3. Definir número de elementos ≤ elementos por folha → mensagem de erro em
   português, preview não quebra.
4. Baixar o PDF e conferir: número de páginas = número de folhas, rodapé
   `Folha i de N` correto, cabimento em A4 na impressão.

## Controle de versão

Trunk Based Development: tudo direto em `main`, sem branches. Um commit por
etapa (funcionalidade + seus testes juntos), com as mensagens indicadas acima.

---

## Avaliação de modelo e de contexto (pedido pelo usuário)

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
basta o estado do repositório mais este arquivo de plano.

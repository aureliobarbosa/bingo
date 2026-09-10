# Bingo — o que falta fazer

> **Andamento** — **o plano acabou.** As dez etapas estão concluídas e o
> projeto está na **1.0**, publicado em **https://bingo410.web.app** (Firebase
> Hosting à frente do Cloud Run), com cada push em `main` implantando sozinho.
> O que resta é o que só o navegador de uma pessoa responde, listado em
> [Conferências pendentes](#conferências-pendentes).

O porquê de cada escolha já feita está em [DECISOES.md](DECISOES.md) — consulte-o
ao mexer numa área pronta; não é preciso lê-lo inteiro para começar uma etapa. O
resumo de uma linha por decisão está no [CLAUDE.md](../CLAUDE.md).

## Onde o projeto está

Serviço *stateless* que gera cartelas de bingo em PDF para impressão: FastAPI e
ReportLab Toolkit no backend, Bootstrap 5 com JavaScript sem build step no frontend. O devcontainer e a imagem de produção saem do mesmo `Dockerfile`, com base única
nos três estágios. Os 84 testes passam e o serviço está publicado no Google Cloud Run.

**Origem das etapas 6.2 a 9:** um briefing produzido numa sessão paralela sobre
hospedagem, servidor e armazenamento, conferido contra o código. Ele confirmou
as decisões da Etapa 8 e acrescentou o arquivo de configuração e a semente; a
conferência revelou os buracos de validação das etapas 6.2 e 6.3.

## Etapa 8 — Publicação

### Carga esperada, que sustenta as decisões abaixo

Um professor usa o gerador cerca de 10 vezes por ano. Com 100 professores são
1.000 sessões por ano, ou **2,7 por dia** — algo como 0,002 requisição por
segundo. Os alunos **não acessam o serviço**: recebem papel impresso. Somado ao
que foi medido no container (47 MB de memória, 0,38 s para gerar 100 folhas), o
dimensionamento é trivial: um único processo `uvicorn` atende com folga de várias
ordens de grandeza.

### 8.3 Limite de taxa, cache e cabeçalhos — **concluída**

Feito nos três commits previstos, com os testes junto (70 no total). O porquê de
cada escolha está em [DECISOES.md](DECISOES.md); em uma linha cada:

- **Limite de taxa por IP** — janela deslizante de 60 s com teto de 120
  requisições, dicionário em memória e biblioteca padrão, só nas rotas `/api/`.
- **Cache dos estáticos** — `EstaticosRevalidados` manda
  `Cache-Control: no-cache`; o ETag resolve a revalidação em 304.
- **Cabeçalhos de segurança** — CSP sem `unsafe-inline`, mais `nosniff`,
  `X-Frame-Options`, `Referrer-Policy` e `Permissions-Policy`.
- **O timeout de geração já existia** — é o `--timeout=60s` do Cloud Run. Um
  timeout dentro do processo foi medido e descartado: com rotas síncronas na
  thread do pool, ele troca o código da resposta sem liberar recurso nenhum.

A CSP era o único item cujo erro seria silencioso, e ela foi conferida no
Firefox pelo usuário: o preview aparece e o console não traz violação nenhuma.
Como isso foi lido está em [DECISOES.md](DECISOES.md).

### 8.4 Endereço público — **concluída**

O serviço atende em **https://bingo410.web.app** (o 410 é a quadra da escola da
primeira professora que usa o gerador). O porquê de cada escolha está em
[DECISOES.md](DECISOES.md), junto com os comandos da configuração; em uma linha
cada:

- **Firebase Hosting, não o domain mapping do Cloud Run** — o nativo está em
  preview e não vale em `southamerica-east1`; um balanceador custaria ~US$ 18/mês.
- **Rewrite `**` e `public` vazio** — estático copiado para lá seria servido
  *antes* do rewrite e divergiria do que o serviço entrega.
- **`_cliente()` lê `Fastly-Client-Ip`** — sem isso o limite de taxa veria a CDN
  inteira como um cliente só. 72 testes.
- **A configuração do lado do Google é manual e de uma vez** — o `firebase.json`
  aponta para o serviço, não para uma versão dele, então nada nele muda a cada
  push.

Falta a conferência da CSP no Firefox pelo endereço novo: a fumaça passou nos
quatro testes e os cabeçalhos atravessaram a CDN inteiros, mas quem obedece à
CSP é o navegador e o erro é silencioso.

---

## Etapa 9 — Configuração em arquivo JSON — **concluída**

Feita nos dois commits previstos, com os testes junto (83 no total). O porquê de
cada escolha está em [DECISOES.md](DECISOES.md); em uma linha cada:

- **Semente do sorteio** — `semente: int | None` em `ConfiguracaoJogo` e um
  `random.Random(cfg.semente)` num caminho único, sem ramo condicional.
- **O preview passa a valer** — `gerar_jogo` sorteia a primeira folha antes de
  qualquer descarte, então ela é a folha do preview; medido idêntico byte a byte
  no fluxo de desenho da página.
- **A semente para em `2**32-1`** — acima de `2**53` o `Number` do JavaScript
  perde precisão e devolveria ao servidor outra semente.
- **"Sortear novamente" troca a semente** — sem isso ele redesenharia a mesma
  cartela e pareceria quebrado.
- **O arquivo é o objeto da API mais `version` e `logo_nome`** — campos extras
  são ignorados pelo Pydantic; nada de novo no backend e nada de novo na CSP.
- **Reuso, não redescoberta** — `baixarBlob` saiu de `baixar()`,
  `aplicarConfiguracao` saiu de `restaurar()`, e importar não pode lançar.

Falta a conferência no navegador pelo usuário: o Node prova a lógica, não o
layout, os eventos nem a CSP.

---

## Etapa 10 — Documentação, estilo e versionamento — **concluída**

Feita em quatro commits, com os testes junto (84 no total). O porquê de cada
escolha está em [DECISOES.md](DECISOES.md); em uma linha cada:

- **A versão tem fonte única** — o `version` do `pyproject.toml`; a página traz
  o marcador `{{versao}}` e `index()` o troca pelo que o `importlib.metadata`
  informa. Ler o `pyproject.toml` em execução não funcionaria: ele não entra na
  imagem de produção.
- **`index()` lê o HTML a cada requisição** — guardá-lo em memória quebraria o
  `--reload`, que observa `.py` e não `.html`.
- **O teste trocou de alvo** — em vez de comparar duas cópias, pede `/` e cobra
  a injeção; conferido que reprova nas duas quebras possíveis.
- **Botões do painel no mesmo azul**, com sombra no hover que se inverte com o
  tema. O par Números/Palavras fica de fora: ali o preenchimento é o que marca
  a escolha.
- **Rodapé com autoria** — ícone do GitHub em SVG embutido, porque a CSP
  barraria `<img>` de outro domínio, e o link do Lattes.
- **Licença MIT** em três lugares que dizem o mesmo: o arquivo, o metadado do
  pacote e o README.
- **README para dois leitores** — o professor que quer usar e quem avalia o
  trabalho —, sem ponteiro para arquivo nenhum do projeto. O repositório não
  recebe PR da comunidade, o que o GitHub ajusta sem arquivar nada.

Falta a imagem da tela: a seção está escrita e comentada no README, esperando o
arquivo em `docs/imagens/tela.png`.

---

## Conferências pendentes

Nenhuma é de código: são as que só o navegador de uma pessoa responde.

1. **A CSP no Firefox pelo endereço novo** (Etapa 8.4). Os cabeçalhos
   atravessam a CDN inteiros e a fumaça passa, mas quem obedece à CSP é o
   navegador e o erro é silencioso. O Firefox é o teste severo: o pdf.js é
   página comum, sujeita à política, enquanto o Chrome desenha PDF por um
   visualizador interno que escapa dela.
2. **A Etapa 9 no navegador** — salvar e abrir o arquivo de configuração, com o
   logo e a semente voltando inteiros.

---

## Verificação

```bash
uv run pytest -q                                    # todos os testes
uv run uvicorn bingo.api:app --reload --host 0.0.0.0   # servidor local
```

Depois, no navegador em `http://localhost:8000` (o `--host 0.0.0.0` é o que
deixa o servidor alcançável de fora do contêiner):
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

### Trabalhar em mais de uma máquina

O desenvolvimento acontece em duas máquinas (laptop e desktop).

- O **git é a fonte de verdade**. `.venv`, imagens Docker e o `localStorage` do
  navegador não viajam — e não precisam.
- Ao começar: `git pull` e `uv sync --frozen`. Ao terminar: **sempre `git push`**,
  senão o trabalho fica preso numa máquina.
- Quem alterar dependências **commita o `uv.lock` junto**; é ele que garante o
  mesmo ambiente dos dois lados.
- O `.devcontainer/` dá ambiente idêntico nas duas máquinas, sem depender do que
  está instalado no sistema.
- O contexto de trabalho viaja em `CLAUDE.md`, `docs/PLANO.md` e
  `docs/DECISOES.md`. **O histórico da conversa não viaja** — por isso toda
  decisão relevante é registrada num desses arquivos antes de trocar de máquina:
  o que falta fazer no plano, o porquê do que já foi feito nas decisões, e o
  resumo de uma linha no `CLAUDE.md`.


# Bingo — o que falta fazer

> **Andamento** — Etapas 8 e 9 concluídas. O serviço está publicado em
> **https://bingo410.web.app** (Firebase Hosting à frente do Cloud Run), cada
> push em `main` implanta sozinho, e a configuração agora tem semente e sai em
> arquivo JSON. **Resta a 10 (documentação).**

O porquê de cada escolha já feita está em [DECISOES.md](DECISOES.md) — consulte-o
ao mexer numa área pronta; não é preciso lê-lo inteiro para começar uma etapa. O
resumo de uma linha por decisão está no [CLAUDE.md](../CLAUDE.md).

## Onde o projeto está

Serviço *stateless* que gera cartelas de bingo em PDF para impressão: FastAPI e
ReportLab Toolkit no backend, Bootstrap 5 com JavaScript sem build step no frontend. O devcontainer e a imagem de produção saem do mesmo `Dockerfile`, com base única
nos três estágios. Os 83 testes passam e o serviço está publicado no Google Cloud Run.

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

## Etapa 10 — Documentação

Escrita depois que o container, o servidor e o arquivo de configuração
estiverem definidos, para descrever o que de fato existe.

`README.md` com: o que é, como rodar localmente
(`uv run uvicorn bingo.api:app --reload --host 0.0.0.0`, com o porquê do
`--host` para quem trabalha no devcontainer), como rodar os testes
(`uv run pytest`),
como construir e executar o container, como está implantado e como usar o
arquivo de configuração.

Commit: `docs: README com instruções de uso e deploy`.

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


# Bingo — o que falta fazer

> **Andamento** — Etapa 8 concluída: o serviço está publicado em
> `https://bingo-286308093839.southamerica-east1.run.app`, cada push em `main`
> implanta sozinho e as proteções que substituem a autenticação estão todas no
> lugar. A Etapa 8.4 fechou o endereço público: o serviço atende em
> **https://bingo410.web.app**, pelo Firebase Hosting. Restam a 9 (arquivo de
> configuração) e a 10 (documentação).

O porquê de cada escolha já feita está em [DECISOES.md](DECISOES.md) — consulte-o
ao mexer numa área pronta; não é preciso lê-lo inteiro para começar uma etapa. O
resumo de uma linha por decisão está no [CLAUDE.md](../CLAUDE.md).

## Onde o projeto está

Serviço *stateless* que gera cartelas de bingo em PDF para impressão: FastAPI e
ReportLab Toolkit no backend, Bootstrap 5 com JavaScript sem build step no frontend. O devcontainer e a imagem de produção saem do mesmo `Dockerfile`, com base única
nos três estágios. Os 58 testes passam e o serviço está publicado no Google Cloud Run.

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
primeira professora que usa o gerador). O domain mapping nativo do Cloud Run não
vale em `southamerica-east1` e um balanceador custaria ~US$ 18/mês; o **Firebase
Hosting** aceita rewrite para Cloud Run nesta região e dá o subdomínio com HTTPS
de graça. O porquê de cada alternativa recusada está em [DECISOES.md](DECISOES.md).

No repositório: `firebase.json` (rewrite `**` para o serviço, `public` vazio de
propósito), `.firebaserc`, e `_cliente()` lendo `Fastly-Client-Ip` — sem isso o
limite de taxa veria a CDN inteira como um cliente só. 72 testes.

**A configuração do lado do Google é manual e de uma vez só**, por decisão: o
`firebase.json` aponta para o *serviço*, não para uma versão dele, então nada
muda a cada push. O `deploy.yml` continua sem papel novo no WIF, e não há
segundo script a manter ao lado do `configura-gcp.sh`. Quem repetir isto noutro
projeto roda, **dentro do container, em `/app`** (é onde o `firebase.json` está,
e o `deploy` o lê do diretório atual; nada a instalar, o container já traz Node
22 com `npx`):

```bash
npx --yes firebase-tools@latest login --no-localhost
npx --yes firebase-tools@latest projects:addfirebase bingol-508013
npx --yes firebase-tools@latest hosting:sites:create bingo410 --project bingol-508013
npx --yes firebase-tools@latest deploy --only hosting
```

Três coisas que custaram tempo e que o comando acima esconde:

- **`--no-localhost` não é detalhe.** Sem ele a CLI sobe um servidor em
  `localhost:9005` *dentro do container* e manda o navegador da máquina ir lá —
  a mesma armadilha do `--host 0.0.0.0` do uvicorn. A credencial fica em
  `/root/.config/`, que não é montado do host: container recriado, login refeito.
- **O `addfirebase` deu 403 três vezes, e não era permissão.** Era a aceitação
  de termos do Firebase, que só existe na interface; o diagnóstico inteiro está
  em [DECISOES.md](DECISOES.md).
- **Nome de site só o `sites:create` decide.** `bingo` e `teacher-bingo`
  estavam reservados, embora respondessem "Site Not Found" por HTTP. Ao trocar
  de nome, trocar junto o campo `site` do `firebase.json` — o `deploy` falha com
  "could not find site" se os dois discordarem.

Verificado no endereço publicado: `scripts/fumaca.sh https://bingo410.web.app`
passou nos quatro testes, e os cabeçalhos de segurança atravessaram a CDN
inteiros. Falta só a conferência da CSP no **Firefox** pelo endereço novo — o
erro é silencioso e só um navegador de verdade responde.

---

## Etapa 9 — Configuração em arquivo JSON

Hoje a configuração fica no `localStorage`, que **não guarda o logo**: alguns MB
estourariam a cota. Ao recarregar a página o logo volta a ser o padrão. Um
arquivo exportável resolve isso e ainda sobrevive a limpeza de navegador, troca
de máquina e atualização da imagem de laboratório pela TI da escola — e pode ser mandado por e-mail para um colega, o que vira compartilhamento sem custo de código.

O `localStorage` **continua**, como conveniência no mesmo navegador; o arquivo é
o caminho durável.

**Semente.** Campo `semente: int | None = None` em `ConfiguracaoJogo`;
`gerador.py` passa a usar `random.Random(cfg.semente)` num caminho único — com
`None` o `Random` sorteia da entropia do sistema, então não há ramo condicional.
Sem semente gravada, regerar a partir de uma configuração salva produz cartelas
diferentes das já impressas, e o arquivo salvo vale pela metade.

A propriedade que faz o preview valer: `gerar_jogo` sorteia a primeira folha
antes de qualquer descarte por repetição, então `gerar_folha` com um
`Random(semente)` recém-criado devolve exatamente a primeira folha do jogo. O
preview passa a mostrar a cartela que vai sair impressa.

Ressalva a registrar junto do código: o Python não garante formalmente que
`random.sample` produza a mesma sequência entre versões. O risco é baixo e o
campo `version` do arquivo dá saída se um dia importar.

**Arquivo.** A mesma forma do objeto que a API já aceita, mais `version: 1` e
`semente`, com o logo como data URI. Exportar com `Blob` +
`URL.createObjectURL` + `<a download>`; importar com `<input type="file">`.

Duas armadilhas já registradas no `CLAUDE.md` valem aqui e devem ser reusadas,
não redescobertas: **limpar o `value` do input depois de ler** e **não aninhar o
`<input>` dentro do `<label>`** que serve de botão. E a importação **não pode
lançar**, pela mesma razão que `restaurar()` não pode: arquivo de outra versão ou
corrompido vira mensagem na interface, não inicialização morta.

**Botão "Sortear novamente"** — ele **já existe** e funciona: é o `#btn-sortear`
no fim do painel lateral, ligado a `atualizarPreview` em `static/app.js`. Hoje
ele sorteia de novo por consequência, não por decisão: sem semente, cada
requisição faz o servidor sortear outra vez. Com a semente, ele passa a **gerar
uma semente nova** antes de atualizar o preview — senão o botão vira um botão
que não faz nada, porque a mesma semente devolve a mesma cartela. Não há botão a
criar; há um comportamento a acrescentar ao que existe.

Commits: um para a semente com seus testes, outro para exportar/importar.

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


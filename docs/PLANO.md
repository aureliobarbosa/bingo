# Bingo — o que falta fazer

> **Andamento** — Etapas 0 a 8.2 concluídas: o serviço está publicado em
> `https://bingo-286308093839.southamerica-east1.run.app` e cada push em `main`
> implanta sozinho. Restam a 8.3 (limite de taxa e cache), a 9 (arquivo de
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

### 8.3 Limite de taxa, cache e cabeçalhos

Os limites de tamanho já foram resolvidos na 6.2.

- **Limite de taxa por IP** — middleware com dicionário em memória e biblioteca
  padrão, seguindo a convenção do projeto. Com `--max-instances 3` o limite
  efetivo é até 3× o configurado e zera quando a instância recicla: serve para
  conter bot em laço, não atacante determinado. Registrar a limitação junto do
  código.
- **Cache dos estáticos** — subclasse de `StaticFiles` enviando
  `Cache-Control: no-cache`, que força revalidação (o ETag resolve em 304).
  Elimina a armadilha do `app.js` velho sem introduzir versão na URL, que
  exigiria o build step que o projeto não tem. Com ~10 usuários por ano,
  revalidar não custa nada.
- **Cabeçalhos de segurança e timeout de geração.** CORS segue desnecessário:
  frontend e API são a mesma origem.
- **nginx está descartado** — ver o motivo em [DECISOES.md](DECISOES.md).

Commits: `chore: limite de taxa por IP`,
`chore: cache dos estáticos`,
`chore: cabeçalhos de segurança`.

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
(`uv run uvicorn bingo.api:app --reload`), como rodar os testes (`uv run pytest`),
como construir e executar o container, como está implantado e como usar o
arquivo de configuração.

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


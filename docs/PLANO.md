# Bingo — o que falta fazer

> **Andamento** — Etapas 0 a 7 concluídas: backend, PDF, API, interface, conexão,
> os refinamentos de 6.1 e o container. Restam a 8.1 (integração contínua), a 8.2
> (publicação no Cloud Run), a 8.3 (cache e segurança) e a 9 (documentação).

O porquê de cada escolha já feita está em [DECISOES.md](DECISOES.md) — consulte-o
ao mexer numa área pronta; não é preciso lê-lo inteiro para começar uma etapa. O
resumo de uma linha por decisão está no [CLAUDE.md](../CLAUDE.md).

## Onde o projeto está

Serviço *stateless* que gera cartelas de bingo em PDF para impressão: FastAPI e
reportlab no backend, Bootstrap 5 com JavaScript sem build step no frontend. O
devcontainer e a imagem de produção saem do mesmo `Dockerfile`, com base única
nos três estágios. Os 52 testes passam. Falta publicar.

---

## Etapa 8 — Integração contínua e publicação

### Carga esperada, que sustenta as decisões abaixo

Um professor usa o gerador cerca de 10 vezes por ano. Com 100 professores são
1.000 sessões por ano, ou **2,7 por dia** — algo como 0,002 requisição por
segundo. Os alunos **não acessam o serviço**: recebem papel impresso. Somado ao
que foi medido no container (47 MB de memória, 0,38 s para gerar 100 folhas), o
dimensionamento é trivial: um único processo `uvicorn` atende com folga de várias
ordens de grandeza.

### 8.1 Integração contínua — **fazer antes do deploy**

`.github/workflows/ci.yml`, disparado em push para `main` e em pull requests:

- **testes** — `astral-sh/setup-uv` com cache, `uv sync --frozen`,
  `uv run pytest -q`;
- **imagem** — constrói o estágio `producao` do `Dockerfile` sem publicar, com
  cache de camadas do próprio Actions, para que uma quebra no container apareça
  aqui e não no meio da configuração do Cloud Run.

Confirmar as versões correntes das actions antes de escrever o arquivo.

Commit: `chore: integração contínua no GitHub Actions`.

### 8.2 Publicação no Google Cloud Run

**Decisão tomada**, com as alternativas avaliadas e descartadas:

| Opção | Por que não |
|---|---|
| Hugging Face Spaces | Sem cartão e o mais fácil de publicar, mas lido como vitrine de demonstração; perde valor como peça de portfólio |
| Render | Dorme em ~15 min e acorda em dezenas de segundos — péssimo para quem abre o link uma vez por mês |
| Azure Container Apps | Equivalente ao Cloud Run, sem vantagem que justifique a troca |
| Fly.io | Modelo gratuito mudou ao longo dos anos; incerto |
| Oracle Always Free | Sempre ligada, mas exige administrar TLS, firewall e atualizações |

Pesou também um critério não técnico: o projeto serve de **portfólio**, e o Cloud
Run comunica competência de operação que uma plataforma de demonstração não
comunica. Vale lembrar, porém, que o diferencial de portfólio não é a plataforma
e sim o que existe em volta — CI, salvaguardas de custo e o registro das decisões.

Trabalho previsto:

1. **Respeitar a variável `PORT`** — o Cloud Run injeta 8080 e o `CMD` fixa 8000.
   É a única mudança de código desta etapa.
2. **Autenticar o Actions por Workload Identity Federation**, sem chave de conta
   de serviço guardada no repositório.
3. Publicar no **Artifact Registry** e implantar no Cloud Run, região
   `southamerica-east1`.
4. **Salvaguardas**, dimensionadas pelo que foi medido: `--memory 256Mi`,
   `--cpu 1`, `--max-instances` baixo, timeout de requisição e alerta de
   orçamento na conta — para que uma anomalia de tráfego não vire fatura.

Verificação: abrir a URL pública, gerar um PDF, conferir páginas e logo, e medir
a partida a frio real.

Commit: `chore: publica o serviço no Cloud Run`.

### 8.3 Segurança e cache

- **nginx está descartado.** Ele não substitui o `uvicorn` — não executa Python;
  seria um proxy *na frente* dele. A plataforma já entrega TLS, domínio e
  roteamento, e a carga projetada dispensa qualquer proxy. Só voltaria a fazer
  sentido numa VPS administrada por nós.
- **Cache dos arquivos estáticos**: `/static/*` é servido sem versão na URL nem
  cabeçalho de cache. Enquanto era só desenvolvimento, o incômodo era limpar o
  cache do navegador; **com deploy, vira defeito** — usuários continuariam
  rodando o `app.js` antigo depois de uma correção. Resolver com versão na URL
  (`/static/app.js?v=…`) ou cabeçalhos adequados.
- Limite de taxa por IP: gerar um jogo cheio é o pedido mais caro, e a rota é
  aberta e sem autenticação — é o vetor de abuso mais óbvio.
- Limite de tamanho do corpo da requisição, cabeçalhos de segurança e timeout de
  geração. CORS segue desnecessário: frontend e API são a mesma origem.

Commit: `chore: cache dos estáticos e limites de segurança`.

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


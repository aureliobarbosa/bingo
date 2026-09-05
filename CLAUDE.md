# Bingo — gerador de cartelas para impressão

Serviço web que gera cartelas de bingo em PDF, prontas para imprimir. O usuário
define os parâmetros num painel lateral e vê a primeira folha como ela sairá na
impressora. Backend Python + FastAPI + reportlab; frontend Bootstrap 5 e
JavaScript sem build step.

O plano completo, com as etapas já feitas e as pendentes, está em
[docs/PLANO.md](docs/PLANO.md). **Leia-o antes de começar qualquer etapa nova.**

## Como rodar

```bash
uv sync                                    # cria o ambiente (baixa o Python 3.14)
uv run pytest -q                           # 52 testes
uv run uvicorn bingo.api:app --reload      # http://127.0.0.1:8000
```

## Convenções de trabalho

- **Trunk Based Development**: trabalhar sempre em `main`, sem branches.
- **Um commit por funcionalidade, com os testes junto.** Mensagens em português,
  no imperativo (`feat:`, `docs:`, `chore:`), explicando o *porquê* no corpo.
- **Checkpoints**: ao terminar uma etapa do plano, parar e pedir avaliação do
  usuário antes de seguir para a próxima.
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
| `src/bingo/gerador.py` | `gerar_jogo(cfg)` → tupla de folhas distintas; cada folha é uma tupla de células em ordem de leitura, com `None` no centro livre |
| `src/bingo/pdf.py` | Desenho em A4 retrato; `desenhar_folha` é compartilhada por `gerar_pdf_folha` e `gerar_pdf_jogo` |
| `src/bingo/api.py` | Rotas `POST /api/preview` (uma folha) e `POST /api/jogo` (PDF completo), `/` e `/static` |
| `static/app.js` | Todo o tráfego HTTP passa pelo objeto `Api`; o resto da interface não conhece o servidor |

Regras de negócio ficam **na dataclass**, não na API: o `ValueError` que ela
levanta vira 422 com a mensagem em português, exibida direto na interface. O
`ConfiguracaoIn` do Pydantic cuida apenas de tipos e faixas.

O serviço é **stateless**: cada requisição traz a configuração completa e recebe
um PDF. Nada é salvo no servidor; a última configuração fica no `localStorage` do
navegador (chaves `bingo.configuracao` e `bingo.tema`).

## Decisões de produto já fechadas

- Grade de linhas × colunas configuráveis; célula central livre só quando ambas
  forem ímpares, e ela recebe o logo (`static/images/logo.jpeg`).
- Download é um **PDF único multi-página**, uma folha por página.
- Sorteio com `random.sample`, sem semente, mas **sem folhas repetidas** dentro de
  um jogo: `gerar_jogo` compara as folhas por `frozenset` e re-sorteia as iguais.
  A folha continua uma tupla ordenada, porque a ordem define a posição na grade.
  Sem isso, um bingo de 12 palavras saía com cartelas idênticas em 64% dos jogos.
- Preview mostra **apenas a primeira folha**, com debounce de 400 ms.
- Bingo de palavras: uma palavra por linha num `<textarea>`.
- Textos com espaço são quebrados em duas linhas, **no espaço mais próximo do
  centro** — sem isso a fonte da folha inteira encolhe por causa do nome mais
  longo.

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
  então `static/` precisa acompanhar a árvore do projeto — instalar apenas o wheel
  deixaria o diretório e o logo de fora. Isso é decisão da Etapa 7 (container).
- **O navegador guarda `static/` em cache.** `StaticFiles` serve sem versão na URL
  nem cabeçalho de cache, então depois de editar `app.js` o navegador pode
  continuar rodando a versão antiga — o que já levou a diagnósticos errados. Ao
  conferir uma mudança na interface, recarregue ignorando o cache
  (`Ctrl+Shift+R`) ou use uma janela anônima. A correção definitiva é decisão da
  Etapa 8.
- **Chrome headless não renderiza PDF** dentro de `iframe`; o `iframe` aparece
  preto nos screenshots mesmo com tudo funcionando. Verifique pelo DOM
  (`preview.src` começa com `blob:`). **Firefox headless não roda neste ambiente**
  (trava até o timeout, inclusive em `about:blank`).

## Verificação da interface sem navegador interativo

O padrão que funcionou: copiar `static/index.html` para um arquivo temporário com
um `<script>` extra ao final, que dirige o formulário e imprime o resultado num
`<pre>`; depois ler com `google-chrome --headless --dump-dom`. Apagar os arquivos
temporários em seguida. Para conferir o PDF impresso, `pdftoppm -png` e ler a
imagem.

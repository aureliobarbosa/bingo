"use strict";

/* Camada de acesso ao servidor: todo o tráfego HTTP da interface passa por aqui. */
const Api = {
  async preview(cfg) {
    return await pedirPdf("/api/preview", cfg);
  },

  async baixarJogo(cfg) {
    return await pedirPdf("/api/jogo", cfg);
  },
};

async function pedirPdf(rota, cfg) {
  const resposta = await fetch(rota, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  if (!resposta.ok) {
    throw new Error(await mensagemDoServidor(resposta));
  }
  return await resposta.blob();
}

/* O backend responde 422 de duas formas: uma regra de negócio devolve `detail`
 * como texto; uma violação de schema devolve uma lista de erros por campo. */
async function mensagemDoServidor(resposta) {
  try {
    const corpo = await resposta.json();
    if (typeof corpo.detail === "string") {
      return corpo.detail;
    }
    if (Array.isArray(corpo.detail)) {
      return corpo.detail
        .map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`)
        .join("; ");
    }
  } catch (erro) {
    /* Resposta sem JSON: cai na mensagem genérica. */
  }
  return `Não foi possível gerar o PDF (erro ${resposta.status}).`;
}

/* ---------------------------------------------------------------- elementos */

const el = {
  form: document.getElementById("form"),
  titulo: document.getElementById("titulo"),
  subtitulo: document.getElementById("subtitulo"),
  numeroElementos: document.getElementById("numero_elementos"),
  palavras: document.getElementById("palavras"),
  linhas: document.getElementById("linhas"),
  colunas: document.getElementById("colunas"),
  centroLivre: document.getElementById("centro_livre"),
  btnLogo: document.getElementById("btn-logo"),
  arquivoLogo: document.getElementById("arquivo_logo"),
  rotuloLogo: document.getElementById("rotulo-logo"),
  numeroFolhas: document.getElementById("numero_folhas"),
  rotuloFolhas: document.getElementById("rotulo-folhas"),
  campoNumeros: document.getElementById("campo-numeros"),
  campoPalavras: document.getElementById("campo-palavras"),
  contagemPalavras: document.getElementById("contagem-palavras"),
  resumo: document.getElementById("resumo"),
  erro: document.getElementById("erro"),
  estado: document.getElementById("estado"),
  preview: document.getElementById("preview"),
  previewVazio: document.getElementById("preview-vazio"),
  btnBaixar: document.getElementById("btn-baixar"),
  btnSortear: document.getElementById("btn-sortear"),
  btnSalvarConfig: document.getElementById("btn-salvar-config"),
  btnAbrirConfig: document.getElementById("btn-abrir-config"),
  arquivoConfig: document.getElementById("arquivo_config"),
  btnTema: document.getElementById("btn-tema"),
  iconeSol: document.getElementById("icone-sol"),
  iconeLua: document.getElementById("icone-lua"),
};

const CHAVE_ARMAZENAMENTO = "bingo.configuracao";
const CHAVE_TEMA = "bingo.tema";
const LOGO_PADRAO = "logo.jpeg";
const FORMATOS_LOGO = ["image/png", "image/jpeg"];
const MAX_LOGO_BYTES = 2 * 1024 * 1024;
const MAX_CELULAS = 100; // precisa acompanhar MAX_CELULAS em src/bingo/models.py
const MAX_ELEMENTOS = 100; // idem, MAX_ELEMENTOS em models.py
const MAX_FOLHAS = 100; // idem, MAX_FOLHAS em models.py
const MAX_PALAVRA_CARACTERES = 50; // idem, MAX_PALAVRA_CARACTERES em models.py
const MAX_SEMENTE = 2 ** 32 - 1; // idem, MAX_SEMENTE em models.py
const ESPERA_LIBERAR_BLOB_MS = 60_000;

/* Versão do arquivo de configuração. Sobe quando o formato mudar de um jeito
 * que esta página não saiba mais ler; é o que permite recusar com uma mensagem
 * em vez de aplicar um arquivo pela metade. */
const VERSAO_CONFIGURACAO = 1;
const NOME_ARQUIVO_CONFIG = "bingo-configuracao.json";

/* Imagem enviada pelo usuário. Fica só em memória: um data URI de alguns MB
 * estouraria a cota do localStorage e derrubaria o resto da configuração. */
let logoEnviado = { nome: LOGO_PADRAO, dados: "" };
let urlAtual = null;

/* Semente do sorteio. Enquanto ela não muda, mexer nos outros campos redesenha
 * a MESMA cartela — e o preview passa a ser literalmente a primeira página do
 * PDF que o botão de baixar entrega. Quem quer outras cartelas pede por
 * "Sortear novamente", que troca a semente. */
let semente = novaSemente();

function novaSemente() {
  return Math.floor(Math.random() * (MAX_SEMENTE + 1));
}

function sementeValida(valor) {
  return Number.isInteger(valor) && valor >= 0 && valor <= MAX_SEMENTE;
}

/* ------------------------------------------------------------ configuração */

function tipoSelecionado() {
  return document.querySelector('input[name="tipo"]:checked').value;
}

function listaDePalavras() {
  return el.palavras.value
    .split("\n")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

function inteiro(campo) {
  const valor = parseInt(campo.value, 10);
  return Number.isNaN(valor) ? 0 : valor;
}

function lerFormulario() {
  return {
    tipo: tipoSelecionado(),
    numero_elementos: inteiro(el.numeroElementos),
    palavras: listaDePalavras(),
    linhas: inteiro(el.linhas),
    colunas: inteiro(el.colunas),
    numero_folhas: inteiro(el.numeroFolhas),
    semente,
    centro_livre: el.centroLivre.checked && !el.centroLivre.disabled,
    logo_enviado: logoEnviado.dados,
    titulo: el.titulo.value,
    subtitulo: el.subtitulo.value,
  };
}

function celulas(cfg) {
  return cfg.linhas * cfg.colunas;
}

function elementosPorFolha(cfg) {
  return celulas(cfg) - (cfg.centro_livre ? 1 : 0);
}

function disponiveis(cfg) {
  return cfg.tipo === "numeros" ? cfg.numero_elementos : cfg.palavras.length;
}

/* Quantas folhas distintas o universo permite: C(n, k), com as folhas tratadas
 * como conjuntos. O produto é interrompido ao passar de MAX_FOLHAS — é o único
 * limite que interessa mostrar, e assim não é preciso BigInt para C(75, 24). */
function combinacoesPossiveis(n, k) {
  if (n <= k) return 0;
  let total = 1;
  const passos = Math.min(k, n - k);
  for (let i = 1; i <= passos; i += 1) {
    total = (total * (n - passos + i)) / i;
    if (total > MAX_FOLHAS) return MAX_FOLHAS;
  }
  return Math.round(total);
}

function maximoDeFolhas(cfg) {
  return Math.min(MAX_FOLHAS, combinacoesPossiveis(disponiveis(cfg), elementosPorFolha(cfg)));
}

/* As mesmas regras do backend, para dar resposta imediata sem ida ao servidor.
 * O backend continua sendo a autoridade: erros dele também são exibidos. */
function validar(cfg) {
  if (cfg.linhas < 1 || cfg.colunas < 1) {
    return "A grade precisa ter ao menos uma linha e uma coluna.";
  }
  if (celulas(cfg) > MAX_CELULAS) {
    return `A grade não pode passar de ${MAX_CELULAS} células (pedido: ${cfg.linhas}x${cfg.colunas} = ${celulas(cfg)}).`;
  }
  if (cfg.numero_folhas < 1 || cfg.numero_folhas > MAX_FOLHAS) {
    return `O número de folhas deve estar entre 1 e ${MAX_FOLHAS}.`;
  }
  if (cfg.tipo === "numeros" && (cfg.numero_elementos < 1 || cfg.numero_elementos > MAX_ELEMENTOS)) {
    return `O número de elementos deve estar entre 1 e ${MAX_ELEMENTOS}.`;
  }
  if (cfg.tipo === "palavras" && cfg.palavras.length > MAX_ELEMENTOS) {
    return `A lista não pode passar de ${MAX_ELEMENTOS} palavras (recebidas: ${cfg.palavras.length}).`;
  }
  if (cfg.tipo === "palavras" && new Set(cfg.palavras).size !== cfg.palavras.length) {
    return "A lista de palavras não pode conter repetições.";
  }
  if (cfg.tipo === "palavras") {
    const longa = cfg.palavras.find((p) => p.length > MAX_PALAVRA_CARACTERES);
    if (longa !== undefined) {
      return `Cada palavra pode ter no máximo ${MAX_PALAVRA_CARACTERES} caracteres ("${longa.slice(0, 20)}…" tem ${longa.length}).`;
    }
  }
  if (disponiveis(cfg) <= elementosPorFolha(cfg)) {
    const limite = disponiveis(cfg) - 1 + (cfg.centro_livre ? 1 : 0);
    return `O número de elementos (${disponiveis(cfg)}) deve ser maior que os elementos por folha (${elementosPorFolha(cfg)}). Com ${disponiveis(cfg)} elementos a grade pode ter no máximo ${limite} ${limite === 1 ? "célula" : "células"}.`;
  }
  const maximo = maximoDeFolhas(cfg);
  if (cfg.numero_folhas > maximo) {
    return `Com ${disponiveis(cfg)} elementos e ${elementosPorFolha(cfg)} por folha existem apenas ${maximo} folhas distintas possíveis.`;
  }
  return null;
}

/* ------------------------------------------------------------------- estado */

function mostrarErro(mensagem) {
  el.erro.textContent = mensagem || "";
  el.erro.hidden = !mensagem;
  el.preview.hidden = Boolean(mensagem);
  el.previewVazio.hidden = !mensagem;
  el.btnBaixar.disabled = Boolean(mensagem);
}

function ocupado(estaOcupado) {
  el.estado.hidden = !estaOcupado;
}

function atualizarMaximoDeFolhas(cfg) {
  const maximo = maximoDeFolhas(cfg);
  el.rotuloFolhas.textContent =
    maximo > 0 ? `Número de folhas (de 1 a ${maximo})` : "Número de folhas";
  el.numeroFolhas.max = String(Math.max(maximo, 1));
}

function atualizarResumo(cfg) {
  const partes = [
    `Grade ${cfg.linhas} × ${cfg.colunas}`,
    `${elementosPorFolha(cfg)} por folha`,
    `${disponiveis(cfg)} disponíveis`,
    `${cfg.numero_folhas} ${cfg.numero_folhas === 1 ? "folha" : "folhas"}`,
  ];
  el.resumo.textContent = partes.join(" · ");
  el.btnBaixar.textContent = `Baixar PDF (${cfg.numero_folhas} ${
    cfg.numero_folhas === 1 ? "folha" : "folhas"
  })`;
}

/* O centro livre só existe quando há uma célula exatamente no meio. */
function ajustarCentroLivre() {
  const impares = inteiro(el.linhas) % 2 === 1 && inteiro(el.colunas) % 2 === 1;
  el.centroLivre.disabled = !impares;
  if (!impares) el.centroLivre.checked = false;
}

function alternarTipo() {
  const numeros = tipoSelecionado() === "numeros";
  el.campoNumeros.hidden = !numeros;
  el.campoPalavras.hidden = numeros;
  el.contagemPalavras.textContent = String(listaDePalavras().length);
}

/* ----------------------------------------------------------------- preview */

/* Libera a URL anterior só depois que o novo documento carregar.
 *
 * Revogando na hora, um navegador configurado para BAIXAR o PDF em vez de
 * exibi-lo fica com o diálogo de download apontando para uma URL que já não
 * existe, e salva um arquivo vazio. O tempo limite é a rede de segurança: no
 * caso do download o `load` nunca vem, e sem ele a URL vazaria. */
function liberarUrlAntiga(url) {
  let liberada = false;
  const liberar = () => {
    if (liberada) return;
    liberada = true;
    URL.revokeObjectURL(url);
  };
  el.preview.addEventListener("load", liberar, { once: true });
  setTimeout(liberar, ESPERA_LIBERAR_BLOB_MS);
}

function exibirPdf(blob) {
  const anterior = urlAtual;
  urlAtual = URL.createObjectURL(blob);
  el.preview.src = urlAtual + "#view=Fit";
  if (anterior) liberarUrlAntiga(anterior);
}

/* Responde na hora a qualquer mudança do formulário: troca os campos
 * visíveis, ajusta o centro livre, atualiza o resumo e valida. Só a geração
 * do PDF é adiada — se isto ficasse junto do preview, o campo de palavras
 * levaria o tempo do debounce para aparecer. */
function sincronizarInterface() {
  ajustarCentroLivre();
  alternarTipo();
  const cfg = lerFormulario();
  atualizarMaximoDeFolhas(cfg);
  atualizarResumo(cfg);
  salvar(cfg);
  const problema = validar(cfg);
  mostrarErro(problema);
  return { cfg, problema };
}

let ultimoPedido = 0;

async function atualizarPreview() {
  const { cfg, problema } = sincronizarInterface();
  if (problema) return;

  const pedido = ++ultimoPedido;
  ocupado(true);
  try {
    const pdf = await Api.preview(cfg);
    if (pedido !== ultimoPedido) return; // chegou atrasado: já há pedido mais novo
    exibirPdf(pdf);
  } catch (erro) {
    if (pedido === ultimoPedido) mostrarErro(erro.message);
  } finally {
    if (pedido === ultimoPedido) ocupado(false);
  }
}

/* Sem trocar a semente este botão redesenharia a mesma cartela, e pareceria
 * quebrado. */
function sortearNovamente() {
  semente = novaSemente();
  atualizarPreview();
}

/* Entrega um blob ao usuário como arquivo. Serve ao PDF e ao arquivo de
 * configuração — dois botões, um caminho só. */
function baixarBlob(blob, nome) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function baixar() {
  const cfg = lerFormulario();
  const problema = validar(cfg);
  if (problema) {
    mostrarErro(problema);
    return;
  }
  ocupado(true);
  const rotulo = el.btnBaixar.textContent;
  el.btnBaixar.disabled = true;
  el.btnBaixar.textContent = "Gerando…";
  try {
    baixarBlob(await Api.baixarJogo(cfg), "bingo.pdf");
  } catch (erro) {
    mostrarErro(erro.message);
  } finally {
    el.btnBaixar.textContent = rotulo;
    el.btnBaixar.disabled = false;
    ocupado(false);
  }
}

/* ------------------------------------------------------------ persistência */

function salvar(cfg) {
  try {
    const { logo_enviado, ...semImagem } = cfg;
    localStorage.setItem(CHAVE_ARMAZENAMENTO, JSON.stringify(semImagem));
  } catch (erro) {
    /* Navegador sem armazenamento disponível: seguir sem lembrar. */
  }
}

/* Não há botão de restaurar padrões: todos os campos são editáveis na tela, e a
 * validação impede salvar configuração inválida. Em compensação, esta função
 * precisa ser à prova de estado estranho — se ela lançar, a inicialização morre
 * no meio e aí sim o usuário fica sem saída pela interface. */
function restaurar() {
  try {
    const cfg = JSON.parse(localStorage.getItem(CHAVE_ARMAZENAMENTO) || "null");
    if (!cfg) return;
    aplicarConfiguracao(cfg);
  } catch (erro) {
    // Estado salvo ilegível ou de outro formato: seguir com os padrões do HTML.
    el.form.reset();
  }
}

/* Escreve uma configuração nos campos da tela. Vale para os dois caminhos de
 * volta: o localStorage, que não guarda o logo, e o arquivo, que guarda. Cada
 * campo ausente mantém o que já estava — assim o arquivo de uma versão mais
 * velha aplica o que tem e não zera o resto. */
function aplicarConfiguracao(cfg) {
  el.titulo.value = cfg.titulo ?? el.titulo.value;
  el.subtitulo.value = cfg.subtitulo ?? "";
  el.numeroElementos.value = cfg.numero_elementos ?? el.numeroElementos.value;
  // Mantém a lista de exemplo do HTML quando nada de útil foi salvo.
  if (Array.isArray(cfg.palavras) && cfg.palavras.length > 0) {
    el.palavras.value = cfg.palavras.join("\n");
  }
  el.linhas.value = cfg.linhas ?? el.linhas.value;
  el.colunas.value = cfg.colunas ?? el.colunas.value;
  el.numeroFolhas.value = cfg.numero_folhas ?? el.numeroFolhas.value;
  // `??` e não `Boolean()`: ausente significa manter o padrão, não desmarcar.
  el.centroLivre.checked = cfg.centro_livre ?? el.centroLivre.checked;
  // Semente salva devolve as mesmas cartelas da sessão anterior; ausente ou
  // estragada, vale a que foi sorteada na carga.
  if (sementeValida(cfg.semente)) semente = cfg.semente;
  const radio = document.getElementById(`tipo-${cfg.tipo}`);
  if (radio) radio.checked = true;
  if (typeof cfg.logo_enviado === "string" && cfg.logo_enviado) {
    logoEnviado = { nome: cfg.logo_nome || "arquivo", dados: cfg.logo_enviado };
    mostrarNomeDoLogo();
  }
}

/* ------------------------------------------------- configuração em arquivo */

/* O localStorage é conveniência no mesmo navegador; o arquivo é o caminho
 * durável. Ele sobrevive a limpeza de navegador, troca de máquina e reimagem
 * do laboratório pela TI da escola, guarda o logo — que não cabe na cota do
 * localStorage — e ainda pode ser mandado por e-mail para um colega. */
function configuracaoParaArquivo() {
  return {
    version: VERSAO_CONFIGURACAO,
    ...lerFormulario(),
    logo_nome: logoEnviado.nome,
  };
}

function exportarConfiguracao() {
  const texto = JSON.stringify(configuracaoParaArquivo(), null, 2);
  const blob = new Blob([texto], { type: "application/json" });
  baixarBlob(blob, NOME_ARQUIVO_CONFIG);
}

function lerComoTexto(arquivo) {
  return new Promise((resolve, rejeitar) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(leitor.result);
    leitor.onerror = () => rejeitar(new Error("Não foi possível ler o arquivo."));
    leitor.readAsText(arquivo);
  });
}

/* As mesmas regras de `_validar_logo` em models.py, aqui aplicadas ao data URI
 * que veio dentro do arquivo — não há um File para medir como no envio. */
function problemaNoLogoSalvo(dados) {
  const separador = dados.indexOf(",");
  const cabecalho = separador < 0 ? "" : dados.slice(0, separador);
  const base64 = separador < 0 ? "" : dados.slice(separador + 1);
  if (!cabecalho.startsWith("data:")) {
    return "O logo do arquivo não está num formato reconhecido.";
  }
  const formato = cabecalho.slice("data:".length).split(";")[0];
  if (!FORMATOS_LOGO.includes(formato)) {
    return `O logo precisa ser PNG ou JPEG (recebido: ${formato || "desconhecido"}).`;
  }
  // base64 gasta 4 caracteres a cada 3 bytes; o '=' final é enchimento.
  const bytes = Math.floor((base64.length * 3) / 4) - (base64.split("=").length - 1);
  if (bytes > MAX_LOGO_BYTES) {
    const megabytes = (bytes / (1024 * 1024)).toFixed(1);
    return `O logo tem ${megabytes} MB e o limite é ${MAX_LOGO_BYTES / (1024 * 1024)} MB.`;
  }
  return null;
}

/* Diz o que impede o arquivo de ser aplicado, ou null se ele serve. */
function problemaNoArquivo(cfg) {
  if (cfg === null || typeof cfg !== "object" || Array.isArray(cfg)) {
    return "O arquivo não parece uma configuração do gerador de bingo.";
  }
  // Sem `version` é arquivo de antes do campo existir: vale como versão 1.
  const versao = cfg.version ?? VERSAO_CONFIGURACAO;
  if (!Number.isInteger(versao) || versao > VERSAO_CONFIGURACAO) {
    return `Este arquivo é da versão ${cfg.version} e esta página lê até a versão ${VERSAO_CONFIGURACAO}.`;
  }
  if (typeof cfg.logo_enviado === "string" && cfg.logo_enviado) {
    return problemaNoLogoSalvo(cfg.logo_enviado);
  }
  return null;
}

/* Pela mesma razão de `restaurar()`, importar não pode lançar: arquivo de outra
 * versão, corrompido ou que nem é JSON vira mensagem na interface. */
async function aoEscolherConfiguracao(evento) {
  // O change do input também borbulha até o form; tratar aqui é suficiente.
  evento.stopPropagation();
  const arquivo = el.arquivoConfig.files[0];
  if (!arquivo) return;

  try {
    const cfg = JSON.parse(await lerComoTexto(arquivo));
    const problema = problemaNoArquivo(cfg);
    if (problema) {
      mostrarErro(problema);
      return;
    }
    aplicarConfiguracao(cfg);
    atualizarPreview();
  } catch (erro) {
    mostrarErro("Não foi possível ler este arquivo de configuração.");
  } finally {
    // Sem isto, escolher o mesmo arquivo de novo não dispara `change` e a
    // interface parece não reagir.
    el.arquivoConfig.value = "";
  }
}

/* --------------------------------------------------------------------- logo */

function mostrarNomeDoLogo() {
  el.rotuloLogo.textContent = `Logo: ${logoEnviado.nome}`;
}

function lerComoDataUri(arquivo) {
  return new Promise((resolve, rejeitar) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(leitor.result);
    leitor.onerror = () => rejeitar(new Error("Não foi possível ler o arquivo."));
    leitor.readAsDataURL(arquivo);
  });
}

/* As mesmas regras do backend, para avisar sem gastar uma viagem ao servidor. */
function problemaNoLogo(arquivo) {
  if (!FORMATOS_LOGO.includes(arquivo.type)) {
    return `O logo precisa ser PNG ou JPEG (recebido: ${arquivo.type || "desconhecido"}).`;
  }
  if (arquivo.size > MAX_LOGO_BYTES) {
    const megabytes = (arquivo.size / (1024 * 1024)).toFixed(1);
    return `O logo tem ${megabytes} MB e o limite é ${MAX_LOGO_BYTES / (1024 * 1024)} MB.`;
  }
  return null;
}

async function aoEscolherLogo(evento) {
  // O change do input também borbulha até o form; tratar aqui é suficiente.
  evento.stopPropagation();
  const arquivo = el.arquivoLogo.files[0];
  if (!arquivo) return;

  const problema = problemaNoLogo(arquivo);
  if (problema) {
    mostrarErro(problema);
    el.arquivoLogo.value = "";
    return;
  }

  try {
    const dados = await lerComoDataUri(arquivo);
    logoEnviado = { nome: arquivo.name, dados };
    mostrarNomeDoLogo();
    atualizarPreview();
  } catch (erro) {
    mostrarErro(erro.message);
  } finally {
    // Sem isto, escolher o mesmo arquivo de novo não dispara `change` e a
    // interface parece não reagir.
    el.arquivoLogo.value = "";
  }
}

/* --------------------------------------------------------------------- tema */

function temaSalvo() {
  try {
    return localStorage.getItem(CHAVE_TEMA);
  } catch (erro) {
    return null;
  }
}

/* Sem escolha salva, segue a preferência do sistema operacional. */
function temaInicial() {
  return (
    temaSalvo() ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );
}

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-bs-theme", tema);
  const noturno = tema === "dark";
  // O botão mostra o ícone do modo para o qual ele leva. Os ícones são SVG, e
  // SVGElement não tem a propriedade `hidden` do HTMLElement — daí o atributo.
  el.iconeSol.toggleAttribute("hidden", !noturno);
  el.iconeLua.toggleAttribute("hidden", noturno);
  el.btnTema.setAttribute(
    "aria-label",
    noturno ? "Mudar para modo diurno" : "Mudar para modo noturno"
  );
  el.btnTema.title = noturno ? "Modo diurno" : "Modo noturno";
  try {
    localStorage.setItem(CHAVE_TEMA, tema);
  } catch (erro) {
    /* Navegador sem armazenamento disponível: seguir sem lembrar. */
  }
}

function alternarTema() {
  const atual = document.documentElement.getAttribute("data-bs-theme");
  aplicarTema(atual === "dark" ? "light" : "dark");
}

/* -------------------------------------------------------------- inicialização */

function comAtraso(funcao, espera) {
  let temporizador;
  return (...args) => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => funcao(...args), espera);
  };
}

const atualizarComAtraso = comAtraso(atualizarPreview, 400);

function aoMudar() {
  sincronizarInterface();
  atualizarComAtraso();
}

el.form.addEventListener("input", aoMudar);
el.form.addEventListener("change", aoMudar);
el.btnBaixar.addEventListener("click", baixar);
el.btnSortear.addEventListener("click", sortearNovamente);
el.btnTema.addEventListener("click", alternarTema);
el.btnLogo.addEventListener("click", () => el.arquivoLogo.click());
el.arquivoLogo.addEventListener("change", aoEscolherLogo);
el.btnSalvarConfig.addEventListener("click", exportarConfiguracao);
el.btnAbrirConfig.addEventListener("click", () => el.arquivoConfig.click());
el.arquivoConfig.addEventListener("change", aoEscolherConfiguracao);

aplicarTema(temaInicial());
mostrarNomeDoLogo();
restaurar();
atualizarPreview();

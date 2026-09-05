"use strict";

/* Camada de acesso ao servidor.
 * Nesta etapa a interface é construída sem backend: os dois métodos devolvem
 * sempre o mesmo PDF de exemplo. Na etapa de conexão só o corpo destes dois
 * métodos muda — o resto do arquivo continua igual. */
const Api = {
  async preview(cfg) {
    return await exemploPdf();
  },

  async baixarJogo(cfg) {
    return await exemploPdf();
  },
};

async function exemploPdf() {
  const resposta = await fetch("/static/exemplo.pdf");
  if (!resposta.ok) throw new Error("Não foi possível carregar o PDF de exemplo.");
  return await resposta.blob();
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
  numeroFolhas: document.getElementById("numero_folhas"),
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
  btnTema: document.getElementById("btn-tema"),
  iconeSol: document.getElementById("icone-sol"),
  iconeLua: document.getElementById("icone-lua"),
};

const CHAVE_ARMAZENAMENTO = "bingo.configuracao";
const CHAVE_TEMA = "bingo.tema";
let urlAtual = null;

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
    centro_livre: el.centroLivre.checked && !el.centroLivre.disabled,
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

/* As mesmas regras do backend, para dar resposta imediata sem ida ao servidor.
 * O backend continua sendo a autoridade: erros dele também são exibidos. */
function validar(cfg) {
  if (cfg.linhas < 1 || cfg.colunas < 1) {
    return "A grade precisa ter ao menos uma linha e uma coluna.";
  }
  if (celulas(cfg) > 100) {
    return `A grade não pode passar de 100 células (pedido: ${cfg.linhas}x${cfg.colunas} = ${celulas(cfg)}).`;
  }
  if (cfg.numero_folhas < 1 || cfg.numero_folhas > 500) {
    return "O número de folhas deve estar entre 1 e 500.";
  }
  if (cfg.tipo === "palavras" && new Set(cfg.palavras).size !== cfg.palavras.length) {
    return "A lista de palavras não pode conter repetições.";
  }
  if (disponiveis(cfg) <= elementosPorFolha(cfg)) {
    const limite = disponiveis(cfg) - 1 + (cfg.centro_livre ? 1 : 0);
    return `O número de elementos (${disponiveis(cfg)}) deve ser maior que os elementos por folha (${elementosPorFolha(cfg)}). Com ${disponiveis(cfg)} elementos a grade pode ter no máximo ${limite} ${limite === 1 ? "célula" : "células"}.`;
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

function exibirPdf(blob) {
  const nova = URL.createObjectURL(blob);
  el.preview.src = nova + "#view=Fit";
  if (urlAtual) URL.revokeObjectURL(urlAtual);
  urlAtual = nova;
}

/* Responde na hora a qualquer mudança do formulário: troca os campos
 * visíveis, ajusta o centro livre, atualiza o resumo e valida. Só a geração
 * do PDF é adiada — se isto ficasse junto do preview, o campo de palavras
 * levaria o tempo do debounce para aparecer. */
function sincronizarInterface() {
  ajustarCentroLivre();
  alternarTipo();
  const cfg = lerFormulario();
  atualizarResumo(cfg);
  salvar(cfg);
  const problema = validar(cfg);
  mostrarErro(problema);
  return { cfg, problema };
}

async function atualizarPreview() {
  const { cfg, problema } = sincronizarInterface();
  if (problema) return;

  ocupado(true);
  try {
    exibirPdf(await Api.preview(cfg));
  } catch (erro) {
    mostrarErro(erro.message);
  } finally {
    ocupado(false);
  }
}

async function baixar() {
  const cfg = lerFormulario();
  const problema = validar(cfg);
  if (problema) {
    mostrarErro(problema);
    return;
  }
  ocupado(true);
  try {
    const blob = await Api.baixarJogo(cfg);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "bingo.pdf";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (erro) {
    mostrarErro(erro.message);
  } finally {
    ocupado(false);
  }
}

/* ------------------------------------------------------------ persistência */

function salvar(cfg) {
  try {
    localStorage.setItem(CHAVE_ARMAZENAMENTO, JSON.stringify(cfg));
  } catch (erro) {
    /* Navegador sem armazenamento disponível: seguir sem lembrar. */
  }
}

function restaurar() {
  let cfg;
  try {
    cfg = JSON.parse(localStorage.getItem(CHAVE_ARMAZENAMENTO) || "null");
  } catch (erro) {
    return;
  }
  if (!cfg) return;

  el.titulo.value = cfg.titulo ?? el.titulo.value;
  el.subtitulo.value = cfg.subtitulo ?? "";
  el.numeroElementos.value = cfg.numero_elementos ?? el.numeroElementos.value;
  // Mantém a lista de exemplo do HTML quando nada de útil foi salvo.
  if (cfg.palavras && cfg.palavras.length > 0) {
    el.palavras.value = cfg.palavras.join("\n");
  }
  el.linhas.value = cfg.linhas ?? el.linhas.value;
  el.colunas.value = cfg.colunas ?? el.colunas.value;
  el.numeroFolhas.value = cfg.numero_folhas ?? el.numeroFolhas.value;
  el.centroLivre.checked = Boolean(cfg.centro_livre);
  const radio = document.getElementById(`tipo-${cfg.tipo}`);
  if (radio) radio.checked = true;
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
el.btnSortear.addEventListener("click", atualizarPreview);
el.btnTema.addEventListener("click", alternarTema);

aplicarTema(temaInicial());
restaurar();
atualizarPreview();

# Bingo410 — gerador de cartelas de bingo

O Bingo 410 surgiu de uma demanda real: a professora Maria Farias, da Escola Classe 410 Norte, usava outra sistema web que não estava atendendo sua demanda. Gerar cartelas de bingo em uma interface simples, configurável e que permitisse que ela o personalizasse com um logo e salvesse diversas configurações para uso posterior.

Atividades simples devem ser fáceis de ser feitas e refeitas.

### 👉 **Acesse neste site: [bingo410.web.app](https://bingo410.web.app)**

## O que ele faz

- Cabeçalho configurável.
- Tamanho da grade configurável: customize o tamanho da tua cartela.
- Bingo de números ou de palavras.
- Logo personalizável: a célula central pode ser trocada por um logo.
- Visualização preliminar: você altera o jogo e vê o resultado como será impresso.
- Salve o seu bingo no seu computador: a configuração de cada jogo (incluindo a logo)  pode ser salva em um arquivo. Compartilhe com seus colegas por e-mail, pen-drive, etc... Isso é um joguinho simples, mas muito divertido e útil.
- Não armazenamos nenhum dado de quem monta os bingos!

## Como foi construído

Este sistema foi construido como  um exercício de desenvolvimento assistido por IA: o
código foi todo escrito em Python, Javascript, HTML e CSS usando **Claude Code**.


O método importa! O trabalho foi organizado plano de trabalho que contém em etapas e subtarefas, cada uma planejada antes de ser escrita e reavaliada depois de pronta. Como o sistema é relativamente simples e  havia apenas um desenvolvedor, adotamos controle de versão com *Trunk Based Development* e *Test Driven Development*. O código em Pthon no backend foi analisado com cuidado. Após estruturar um plano global cada tarefa gerou um *commit*, que é um passo no controle de versões.

Ao longo de cada tarefa uma série de decisões foram tomadas e estas são guardadas em um arquivo específico. Ao longo do caminho vários problemas foram encontrados, que demandaram tomadas de decisões sobre, automatizadas ou não, que foram registradas em um arquivo markdown indicado o porque de cada decisão em cada etapa. Eventualmente foi necessário voltar atrás e refazer alguma tarefa e estes arquivos contendo planejamento, decisões e armadilhas encontradas ajudam a máquina a não esbarrar nas mesmas questões ou refazer o mesmo erro. Caminhos considerados e descartados também são anotados nas armadilhas pois eles custam tempo de processamento computacional e análise humana.

São esses registros que permitem a uma sessão nova retomar o trabalho onde a
anterior parou, sem repetir o diagnóstico anterior.

## Tecnologias utilizadas

| | |
|---|---|
| Backend | Python 3.14, FastAPI, ReportLab, Pillow |
| Frontend | Bootstrap 5 e JavaScript, sem build step |
| Ferramental | uv, ruff, pytest |
| Publicação | Docker, GitHub Actions, Google Cloud Run, Firebase Hosting |

O serviço é *stateless*: cada requisição leva a configuração inteira e recebe
um PDF de volta. Nada é guardado no servidor — nem cadastro, nem cartela, nem
o logo enviado.

## Quer rodar esse código localmente?



```bash
uv sync
uv run uvicorn bingo.api:app --reload --host 0.0.0.0
```

A página fica em `http://localhost:8000`.

## Licença e contribuições

Software livre sob licença MIT. Caso queira trabalhar neste projeto, faça um fork. Qualquer dúvida entre em contato com o desenvolvedor.

## Autoria

Marco Aurélio Alves Barbosa (UnB) —
[GitHub](https://github.com/aureliobarbosa) ·
[Currículo Lattes](https://lattes.cnpq.br/5720622055548812)

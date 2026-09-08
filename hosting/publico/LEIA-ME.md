# Diretório vazio de propósito

O Firebase Hosting exige a chave `public` no `firebase.json` mesmo quando não
há arquivo estático nenhum para publicar. Tudo o que a página precisa —
`index.html`, `app.js`, o logo — é servido pelo próprio serviço no Cloud Run,
para onde o rewrite `**` manda toda requisição.

**Não coloque cópias de `static/` aqui.** O Hosting resolve arquivo estático
*antes* de aplicar o rewrite: uma cópia neste diretório passaria por cima do
que o serviço entrega, e as duas divergiriam no primeiro `app.js` alterado.

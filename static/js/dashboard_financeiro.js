(() => {
    const canvas = document.getElementById("grafico-fluxo-caixa");
    const fonte = document.getElementById("dados-grafico-fluxo-caixa");
    if (!canvas || !fonte) return;
    const dados = JSON.parse(fonte.textContent);
    const contexto = canvas.getContext("2d");
    const cores = ["#027a48", "#b42318", "#12b76a", "#f79009", "#1f4e79"];

    function desenhar() {
        const largura = Math.max(canvas.parentElement.clientWidth, dados.length * 90, 720);
        const altura = 340;
        const escala = window.devicePixelRatio || 1;
        canvas.width = largura * escala;
        canvas.height = altura * escala;
        canvas.style.width = `${largura}px`;
        canvas.style.height = `${altura}px`;
        contexto.setTransform(escala, 0, 0, escala, 0, 0);
        contexto.clearRect(0, 0, largura, altura);

        const margem = {topo: 38, direita: 24, base: 52, esquerda: 55};
        const areaLargura = largura - margem.esquerda - margem.direita;
        const areaAltura = altura - margem.topo - margem.base;
        const chaves = ["entradas_realizadas", "saidas_realizadas", "entradas_previstas", "saidas_previstas", "saldo_projetado"];
        const valores = dados.flatMap(item => chaves.map(chave => item[chave]));
        const maior = Math.max(...valores, 1);
        const menor = Math.min(...valores, 0);
        const amplitude = maior - menor || 1;
        const y = valor => margem.topo + ((maior - valor) / amplitude) * areaAltura;
        const zeroY = y(0);
        contexto.strokeStyle = "#d0d5dd";
        contexto.beginPath(); contexto.moveTo(margem.esquerda, zeroY); contexto.lineTo(largura - margem.direita, zeroY); contexto.stroke();
        if (!dados.length) return;

        const grupo = areaLargura / dados.length;
        const barra = Math.min(13, grupo / 7);
        dados.forEach((item, indice) => {
            const centro = margem.esquerda + grupo * indice + grupo / 2;
            chaves.slice(0, 4).forEach((chave, serie) => {
                const valor = item[chave];
                contexto.fillStyle = cores[serie];
                contexto.fillRect(centro + (serie - 1.5) * (barra + 2) - barra / 2, Math.min(y(valor), zeroY), barra, Math.max(Math.abs(y(valor) - zeroY), 1));
            });
            contexto.fillStyle = "#667085"; contexto.font = "11px Inter, sans-serif"; contexto.textAlign = "center"; contexto.fillText(item.rotulo, centro, altura - 22);
        });

        contexto.strokeStyle = cores[4]; contexto.lineWidth = 2; contexto.beginPath();
        dados.forEach((item, indice) => {
            const x = margem.esquerda + grupo * indice + grupo / 2;
            const pontoY = y(item.saldo_projetado);
            if (indice === 0) contexto.moveTo(x, pontoY); else contexto.lineTo(x, pontoY);
        });
        contexto.stroke();

        const legendas = ["Entradas realizadas", "Saídas realizadas", "Entradas previstas", "Saídas previstas", "Saldo projetado"];
        contexto.font = "10px Inter, sans-serif"; contexto.textAlign = "left";
        legendas.forEach((legenda, indice) => {
            const x = margem.esquerda + indice * 132;
            contexto.fillStyle = cores[indice]; contexto.fillRect(x, 7, 10, 10);
            contexto.fillStyle = "#344054"; contexto.fillText(legenda, x + 14, 16);
        });
    }
    desenhar();
    window.addEventListener("resize", desenhar);
})();

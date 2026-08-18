(() => {
    const canvas = document.getElementById("grafico-resultado-obra");
    const dadosElement = document.getElementById("dados-grafico-resultado-obra");

    if (!canvas || !dadosElement) return;

    const dados = JSON.parse(dadosElement.textContent);
    const contexto = canvas.getContext("2d");
    const cores = ["#027a48", "#b42318", "#1f4e79"];

    function desenhar() {
        const largura = Math.max(
            canvas.parentElement.clientWidth,
            dados.length * 75,
            640,
        );
        const altura = 320;
        const escala = window.devicePixelRatio || 1;
        canvas.width = largura * escala;
        canvas.height = altura * escala;
        canvas.style.width = `${largura}px`;
        canvas.style.height = `${altura}px`;
        contexto.setTransform(escala, 0, 0, escala, 0, 0);
        contexto.clearRect(0, 0, largura, altura);

        const margem = {topo: 28, direita: 20, base: 54, esquerda: 60};
        const areaLargura = largura - margem.esquerda - margem.direita;
        const areaAltura = altura - margem.topo - margem.base;
        const valores = dados.flatMap(item => [
            item.receitas,
            item.custos_despesas,
            item.resultado,
        ]);
        const maior = Math.max(...valores, 1);
        const menor = Math.min(...valores, 0);
        const amplitude = maior - menor || 1;
        const y = valor => margem.topo + ((maior - valor) / amplitude) * areaAltura;
        const zeroY = y(0);

        contexto.strokeStyle = "#d0d5dd";
        contexto.beginPath();
        contexto.moveTo(margem.esquerda, zeroY);
        contexto.lineTo(largura - margem.direita, zeroY);
        contexto.stroke();

        if (!dados.length) return;
        const grupo = areaLargura / dados.length;
        const barra = Math.min(18, grupo / 5);

        dados.forEach((item, indice) => {
            const centro = margem.esquerda + grupo * indice + grupo / 2;
            [item.receitas, item.custos_despesas, item.resultado].forEach(
                (valor, serie) => {
                    contexto.fillStyle = cores[serie];
                    const topo = Math.min(y(valor), zeroY);
                    const tamanho = Math.max(Math.abs(y(valor) - zeroY), 1);
                    contexto.fillRect(
                        centro + (serie - 1) * (barra + 3) - barra / 2,
                        topo,
                        barra,
                        tamanho,
                    );
                }
            );
            contexto.fillStyle = "#667085";
            contexto.font = "11px Inter, sans-serif";
            contexto.textAlign = "center";
            contexto.fillText(item.rotulo, centro, altura - 25);
        });

        const legendas = ["Receitas", "Custos + Despesas", "Resultado"];
        contexto.textAlign = "left";
        legendas.forEach((legenda, indice) => {
            const x = margem.esquerda + indice * 150;
            contexto.fillStyle = cores[indice];
            contexto.fillRect(x, 5, 12, 12);
            contexto.fillStyle = "#344054";
            contexto.fillText(legenda, x + 18, 15);
        });
    }

    desenhar();
    window.addEventListener("resize", desenhar);
})();

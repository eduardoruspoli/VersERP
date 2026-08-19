document.addEventListener("DOMContentLoaded", () => {
    const formulario = document.querySelector(".solicitacao-form");
    const obra = document.getElementById("id_obra");
    if (!formulario || !obra) return;

    async function carregarItens() {
        const seletores = [...document.querySelectorAll(".item-previsto")];
        const selecionados = seletores.map((campo) => campo.value);
        seletores.forEach((campo) => campo.replaceChildren(new Option("Item não previsto / selecionar item aprovado", "")));
        if (!obra.value) return;
        const url = formulario.dataset.itensUrl.replace("/0/", `/${obra.value}/`);
        const resposta = await fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}});
        if (!resposta.ok) return;
        const dados = await resposta.json();
        seletores.forEach((campo, indice) => {
            dados.itens.forEach((item) => {
                const opcao = new Option(`${item.descricao} — ${item.quantidade} ${item.unidade}`, item.id);
                opcao.dataset.descricao = item.descricao;
                opcao.dataset.unidade = item.unidade;
                campo.add(opcao);
            });
            campo.value = selecionados[indice];
        });
    }

    document.addEventListener("change", (evento) => {
        if (!evento.target.classList.contains("item-previsto")) return;
        const bloco = evento.target.closest(".solicitacao-item");
        const opcao = evento.target.selectedOptions[0];
        if (evento.target.value) {
            bloco.querySelector(".descricao-item").value ||= opcao.dataset.descricao || "";
            bloco.querySelector(".tipo-origem").value = "PREVISTO";
            const unidade = bloco.querySelector('input[name$="-unidade"]');
            unidade.value ||= opcao.dataset.unidade || "";
        } else {
            bloco.querySelector(".tipo-origem").value = "NAO_PREVISTO";
        }
    });
    obra.addEventListener("change", carregarItens);
    carregarItens();
});

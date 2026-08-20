document.addEventListener("DOMContentLoaded", () => {
    const formulario = document.querySelector(".solicitacao-form");
    const obra = document.getElementById("id_obra");
    const itens = document.getElementById("solicitacao-itens");
    const totalForms = document.getElementById("id_itens-TOTAL_FORMS");
    const template = document.getElementById("item-form-template");
    const adicionar = document.getElementById("adicionar-item");
    if (!formulario || !obra || !itens || !totalForms) return;

    function numerarItens() {
        let numero = 1;
        itens.querySelectorAll(".solicitacao-item").forEach((bloco) => {
            if (bloco.hidden) return;
            const destino = bloco.querySelector(".item-numero");
            if (destino) destino.textContent = numero++;
        });
    }

    async function carregarItensNoCampo(campo, valorAtual = "") {
        campo.replaceChildren(new Option("Item não previsto / selecionar item aprovado", ""));
        if (!obra.value) return;
        const url = formulario.dataset.itensUrl.replace("/0/", `/${obra.value}/`);
        const resposta = await fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}});
        if (!resposta.ok) return;
        const dados = await resposta.json();
        dados.itens.forEach((item) => {
            const opcao = new Option(`${item.descricao} — ${item.quantidade} ${item.unidade}`, item.id);
            opcao.dataset.descricao = item.descricao;
            opcao.dataset.unidade = item.unidade;
            campo.add(opcao);
        });
        campo.value = valorAtual;
    }

    async function carregarItens() {
        const seletores = [...itens.querySelectorAll(".item-previsto")];
        await Promise.all(seletores.map((campo) => carregarItensNoCampo(campo, campo.value)));
    }

    adicionar?.addEventListener("click", async () => {
        const indice = Number(totalForms.value);
        const fragmento = template.content.cloneNode(true);
        const bloco = fragmento.querySelector(".solicitacao-item");
        bloco.innerHTML = bloco.innerHTML.replaceAll("__prefix__", String(indice));
        bloco.dataset.formIndex = indice;
        itens.appendChild(fragmento);
        totalForms.value = indice + 1;
        const seletor = itens.lastElementChild.querySelector(".item-previsto");
        if (seletor) await carregarItensNoCampo(seletor);
        numerarItens();
        itens.lastElementChild.querySelector("input, select, textarea")?.focus();
    });

    itens.addEventListener("click", (evento) => {
        const botao = evento.target.closest(".remover-item");
        if (!botao) return;
        const bloco = botao.closest(".solicitacao-item");
        const excluir = bloco.querySelector('input[name$="-DELETE"]');
        const id = bloco.querySelector('input[name$="-id"]');
        if (id?.value && excluir) {
            excluir.checked = true;
            bloco.hidden = true;
        } else {
            bloco.remove();
        }
        numerarItens();
    });

    itens.addEventListener("change", (evento) => {
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
    numerarItens();
    carregarItens();
});

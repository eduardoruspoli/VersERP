document.addEventListener("DOMContentLoaded", () => {
  const secao=document.querySelector("[data-classificacoes]"); if(!secao) return;
  const alternador=document.querySelector("[name=classificacao_multipla]");
  const linhas=secao.querySelector("[data-classificacoes-linhas]");
  const corpo=secao.querySelector("[data-classificacoes-body]");
  const totalForms=secao.querySelector("[name=classificacoes-TOTAL_FORMS]");
  const valorTotal=document.querySelector("[name=valor_total]");
  const numero=(valor)=>{let t=String(valor||"").replace(/\s|R\$/g,"");if(t.includes(","))t=t.replace(/\./g,"").replace(",", ".");return Number.parseFloat(t)||0};
  const moeda=(valor)=>valor.toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
  function atualizar(){linhas.hidden=!alternador.checked;let total=0;corpo.querySelectorAll(".classificacao-valor").forEach(c=>{const linha=c.closest("tr");const apagar=linha.querySelector("[name$=-DELETE]");if(!apagar||!apagar.checked)total+=numero(c.value)});secao.querySelector("[data-total-classificado]").textContent=moeda(total);secao.querySelector("[data-saldo-classificacao]").textContent=moeda(numero(valorTotal?.value)-total)}
  alternador.addEventListener("change",atualizar);secao.addEventListener("input",atualizar);
  secao.querySelector("[data-adicionar-classificacao]").addEventListener("click",()=>{const indice=Number(totalForms.value);const html=secao.querySelector("[data-classificacao-template]").innerHTML.replaceAll("__prefix__",indice);corpo.insertAdjacentHTML("beforeend",html);totalForms.value=indice+1;atualizar()});
  atualizar();
});

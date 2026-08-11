document.addEventListener("DOMContentLoaded", function () {

    const campoDocumento = document.getElementById("id_cpf_cnpj");
    const campoTipoPessoa = document.getElementById("id_tipo_pessoa");

    const botaoConsultar = document.getElementById("btn-consultar-cnpj");
    const statusConsulta = document.getElementById("cnpj-status");
    const labelDocumento = document.getElementById("label-cpf-cnpj");


    function atualizarTipoDocumento() {

        if (!campoTipoPessoa || !campoDocumento) {
            return;
        }

        const tipoPessoa = campoTipoPessoa.value;

        if (tipoPessoa === "PF") {

            labelDocumento.textContent = "CPF";

            campoDocumento.placeholder = "000.000.000-00";
            campoDocumento.maxLength = 14;

            if (botaoConsultar) {
                botaoConsultar.style.display = "none";
            }

            if (statusConsulta) {
                statusConsulta.textContent = "";
            }

        } else {

            labelDocumento.textContent = "CNPJ";

            campoDocumento.placeholder = "00.000.000/0000-00";
            campoDocumento.maxLength = 18;

            if (botaoConsultar) {
                botaoConsultar.style.display = "inline-flex";
            }

        }

        aplicarMascaraDocumento();
    }


    function aplicarMascaraDocumento() {

        if (!campoDocumento) {
            return;
        }

        let valor = campoDocumento.value.replace(/\D/g, "");

        const tipoPessoa = campoTipoPessoa
            ? campoTipoPessoa.value
            : "PJ";


        if (tipoPessoa === "PF") {

            valor = valor.slice(0, 11);

            valor = valor.replace(
                /(\d{3})(\d)/,
                "$1.$2"
            );

            valor = valor.replace(
                /(\d{3})(\d)/,
                "$1.$2"
            );

            valor = valor.replace(
                /(\d{3})(\d{1,2})$/,
                "$1-$2"
            );

        } else {

            valor = valor.slice(0, 14);

            valor = valor.replace(
                /^(\d{2})(\d)/,
                "$1.$2"
            );

            valor = valor.replace(
                /^(\d{2})\.(\d{3})(\d)/,
                "$1.$2.$3"
            );

            valor = valor.replace(
                /\.(\d{3})(\d)/,
                ".$1/$2"
            );

            valor = valor.replace(
                /(\d{4})(\d)/,
                "$1-$2"
            );

        }

        campoDocumento.value = valor;
    }


    if (campoTipoPessoa) {

        campoTipoPessoa.addEventListener(
            "change",
            function () {

                campoDocumento.value = "";

                atualizarTipoDocumento();

            }
        );

    }


    if (campoDocumento) {

        campoDocumento.addEventListener(
            "input",
            aplicarMascaraDocumento
        );

    }


    if (botaoConsultar) {

        botaoConsultar.addEventListener(
            "click",
            async function () {

                const cnpj = campoDocumento.value.replace(
                    /\D/g,
                    ""
                );


                if (cnpj.length !== 14) {

                    statusConsulta.textContent =
                        "Informe um CNPJ válido com 14 dígitos.";

                    statusConsulta.className =
                        "form-text error";

                    return;
                }


                botaoConsultar.disabled = true;

                statusConsulta.textContent =
                    "Consultando CNPJ...";

                statusConsulta.className =
                    "form-text";


                try {

                    const resposta = await fetch(
                        `/pessoas/consultar-cnpj/?cnpj=${cnpj}`
                    );

                    const dados = await resposta.json();


                    if (!resposta.ok) {

                        throw new Error(
                            dados.erro ||
                            "Erro ao consultar CNPJ."
                        );

                    }


                    preencherCampo(
                        "id_razao_social",
                        dados.razao_social
                    );

                    preencherCampo(
                        "id_nome_fantasia",
                        dados.nome_fantasia
                    );

                    preencherCampo(
                        "id_cep",
                        dados.cep
                    );

                    preencherCampo(
                        "id_endereco",
                        dados.endereco
                    );

                    preencherCampo(
                        "id_numero",
                        dados.numero
                    );

                    preencherCampo(
                        "id_complemento",
                        dados.complemento
                    );

                    preencherCampo(
                        "id_bairro",
                        dados.bairro
                    );

                    preencherCampo(
                        "id_cidade",
                        dados.cidade
                    );

                    preencherCampo(
                        "id_estado",
                        dados.estado
                    );

                    preencherCampo(
                        "id_telefone",
                        dados.telefone
                    );

                    preencherCampo(
                        "id_email",
                        dados.email
                    );


                    statusConsulta.textContent =
                        "Dados encontrados e preenchidos.";

                    statusConsulta.className =
                        "form-text success";

                } catch (erro) {

                    statusConsulta.textContent =
                        erro.message;

                    statusConsulta.className =
                        "form-text error";

                } finally {

                    botaoConsultar.disabled = false;

                }

            }
        );

    }


    function preencherCampo(id, valor) {

        if (!valor) {
            return;
        }

        const campo = document.getElementById(id);

        if (campo) {
            campo.value = valor;
        }

    }


    atualizarTipoDocumento();

});
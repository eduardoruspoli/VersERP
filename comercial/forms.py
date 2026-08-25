from django import forms
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import Q
import re

from financeiro.models import Empresa
from financeiro.models import PlanoConta
from pessoas.models import Pessoa
from core.access import empresas_usuario

from .models import HistoricoContatoProposta, Proposta, PropostaItem, PropostaLinhaPublica, PropostaRevisao, PropostaTributo


class ClasseCssMixin:
    def aplicar_classes(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-select" if isinstance(field.widget, forms.Select) else "form-control")


class PropostaCriacaoForm(ClasseCssMixin, forms.Form):
    empresa = forms.ModelChoiceField(Empresa.objects.filter(ativa=True))
    codigo = forms.CharField(label="Número da proposta", max_length=20, help_text="Ex.: VERS1917")
    cliente = forms.ModelChoiceField(Pessoa.objects.filter(ativo=True).filter(Q(classificacao="CLIENTE") | Q(classificacao="AMBOS")))
    nome_servico = forms.CharField(max_length=250)

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["empresa"].queryset = empresas_usuario(usuario, ativas=True)
        self.aplicar_classes()

    def clean_codigo(self):
        codigo = "".join(self.cleaned_data["codigo"].upper().split())
        if not codigo.startswith("VERS") or not codigo[4:].isdigit():
            raise forms.ValidationError("Informe o número no padrão VERS seguido de algarismos, por exemplo VERS1917.")
        return codigo

    def clean(self):
        dados = super().clean()
        if dados.get("empresa") and dados.get("codigo") and Proposta.objects.filter(empresa=dados["empresa"], codigo=dados["codigo"]).exists():
            self.add_error("codigo", "Já existe uma proposta com este número nesta empresa.")
        return dados


class PropostaRevisaoForm(ClasseCssMixin, forms.ModelForm):
    codigo = forms.CharField(
        label="Número da proposta",
        max_length=20,
        help_text="Ex.: VERS1927",
    )
    cliente = forms.ModelChoiceField(
        label="Cliente",
        queryset=Pessoa.objects.none(),
    )

    class Meta:
        model = PropostaRevisao
        exclude = ["proposta", "numero", "modelo_conteudo", "congelada", "enviada_em", "criado_por", "criado_em", "empresa_nome_snapshot", "empresa_documento_snapshot", "cliente_nome_snapshot", "cliente_documento_snapshot"]
        widgets = {campo: forms.Textarea(attrs={"rows": 3}) for campo in ("escopo_incluido", "nao_incluso", "texto_introdutorio", "normas_procedimentos", "qualificacao_mao_obra", "obrigacoes_contratada", "observacoes_comerciais", "condicao_pagamento", "observacoes_internas")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Pessoa.objects.filter(ativo=True).filter(
            Q(classificacao="CLIENTE") | Q(classificacao="AMBOS")
        )
        if self.instance and self.instance.pk:
            self.fields["codigo"].initial = self.instance.proposta.codigo
            self.fields["cliente"].initial = self.instance.proposta.cliente_id
        self.fields["formacao_preco"].label = "Método de formação do preço"
        self.fields["formacao_preco"].choices = [
            (PropostaRevisao.FormacaoPreco.MARKUP, "Margem sobre fornecedor (como na planilha)"),
            (PropostaRevisao.FormacaoPreco.MARGEM, "Margem sobre venda (legado)"),
            (PropostaRevisao.FormacaoPreco.MANUAL, "Preço manual"),
        ]
        self.fields["percentual_formacao"].label = "Margem de formação padrão (%)"
        self.fields["percentual_formacao"].help_text = (
            "Usada nos itens que não tenham margem própria. Ex.: 86% transforma R$ 125,00 em R$ 232,50."
        )
        self.aplicar_classes()

    def clean_codigo(self):
        codigo = "".join(self.cleaned_data["codigo"].upper().split())
        if not codigo.startswith("VERS") or not codigo[4:].isdigit():
            raise forms.ValidationError(
                "Informe o número no padrão VERS seguido de algarismos, por exemplo VERS1927."
            )
        if self.instance and self.instance.pk:
            proposta = self.instance.proposta
            if Proposta.objects.filter(empresa_id=proposta.empresa_id, codigo=codigo).exclude(pk=proposta.pk).exists():
                raise forms.ValidationError("Já existe uma proposta com este número nesta empresa.")
        return codigo

    def save(self, commit=True):
        revisao = super().save(commit=commit)
        proposta = revisao.proposta
        cliente = self.cleaned_data.get("cliente")
        codigo = self.cleaned_data.get("codigo")
        campos_proposta = []

        if cliente and proposta.cliente_id != cliente.pk:
            proposta.cliente = cliente
            campos_proposta.append("cliente")

        if codigo and proposta.codigo != codigo:
            proposta.codigo = codigo
            proposta.numero_sequencial = int(codigo[4:])
            campos_proposta.extend(["codigo", "numero_sequencial"])

        if commit and campos_proposta:
            proposta.save(update_fields=[*campos_proposta, "atualizado_em"])
        return revisao


class PropostaItemForm(ClasseCssMixin, forms.ModelForm):
    TIPOS_SERVICO = {PropostaItem.Tipo.MAO_OBRA, PropostaItem.Tipo.SERVICO_TERCEIRO, PropostaItem.Tipo.JUROS_ANTECIPACAO}

    class Meta:
        model = PropostaItem
        fields = [
            "tipo", "descricao", "quantidade", "unidade", "fornecedor",
            "custo_unitario", "margem_formacao", "taxa_juros_mensal", "prazo_antecipacao_dias",
        ]
        labels = {
            "tipo": "Tipo",
            "descricao": "Descrição",
            "quantidade": "Quantidade",
            "unidade": "Unidade",
            "fornecedor": "Fornecedor",
            "custo_unitario": "Valor unitário fornecedor",
            "margem_formacao": "Margem (%)",
            "taxa_juros_mensal": "Taxa mensal (%)",
            "prazo_antecipacao_dias": "Prazo (dias)",
        }

    def __init__(self, *args, grupo=None, revisao=None, **kwargs):
        self.revisao_contexto = revisao
        super().__init__(*args, **kwargs)
        if grupo == "servico":
            permitidos = [
                PropostaItem.Tipo.MAO_OBRA,
                PropostaItem.Tipo.SERVICO_TERCEIRO,
                PropostaItem.Tipo.JUROS_ANTECIPACAO,
            ]
            self.fields["tipo"].choices = [c for c in PropostaItem.Tipo.choices if c[0] in permitidos]
            self.fields["tipo"].initial = PropostaItem.Tipo.MAO_OBRA
        elif grupo == "material":
            permitidos = [c[0] for c in PropostaItem.Tipo.choices if c[0] not in self.TIPOS_SERVICO]
            self.fields["tipo"].choices = [c for c in PropostaItem.Tipo.choices if c[0] in permitidos]
            self.fields["tipo"].initial = PropostaItem.Tipo.MATERIAL
        self.aplicar_classes()
        self.fields["margem_formacao"].help_text = "Ex.: 86% sobre R$ 125,00 gera R$ 232,50 de valor unitário de venda."
        self.fields["taxa_juros_mensal"].initial = self.instance.taxa_juros_mensal if self.instance and self.instance.pk else Decimal("2.4")
        if revisao and not (self.instance and self.instance.pk) and not self.initial.get("prazo_antecipacao_dias"):
            match = re.search(r"(\d{1,4})\s*dias?", revisao.condicao_pagamento or "", flags=re.IGNORECASE)
            if match:
                self.fields["prazo_antecipacao_dias"].initial = int(match.group(1))
        self.fields["taxa_juros_mensal"].help_text = "Juros de antecipação: padrão 2,40% ao mês."
        self.fields["prazo_antecipacao_dias"].help_text = "Use o prazo de pagamento. Ex.: 90 dias = 3 meses; 180 dias = 6 meses."
        if grupo == "servico":
            for nome in ("quantidade", "unidade", "fornecedor", "custo_unitario", "margem_formacao"):
                self.fields[nome].required = False
        self.fields["fornecedor"].queryset = Pessoa.objects.filter(ativo=True).filter(Q(classificacao="FORNECEDOR") | Q(classificacao="AMBOS"))

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        if tipo == PropostaItem.Tipo.JUROS_ANTECIPACAO:
            dados["quantidade"] = Decimal("1")
            dados["unidade"] = "VB"
            dados["fornecedor"] = None
            dados["custo_unitario"] = Decimal("0")
            dados["margem_formacao"] = Decimal("0")
            if not dados.get("taxa_juros_mensal"):
                self.add_error("taxa_juros_mensal", "Informe a taxa mensal de antecipação.")
            if not dados.get("prazo_antecipacao_dias"):
                self.add_error("prazo_antecipacao_dias", "Informe o prazo em dias.")
        else:
            for nome, mensagem in (
                ("quantidade", "Informe a quantidade."),
                ("unidade", "Informe a unidade."),
                ("custo_unitario", "Informe o valor unitário do fornecedor."),
            ):
                if dados.get(nome) in (None, ""):
                    self.add_error(nome, mensagem)
            dados["taxa_juros_mensal"] = None
            dados["prazo_antecipacao_dias"] = None
        return dados


class PropostaLinhaPublicaForm(ClasseCssMixin, forms.ModelForm):
    class Meta:
        model = PropostaLinhaPublica
        exclude = ["revisao", "origem_automatica", "valor_automatico", "oculta_manual"]
        labels = {
            "grupo": "Grupo",
            "descricao": "Nome/descrição para o cliente",
            "valor_total": "Valor público",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class PropostaTributoForm(ClasseCssMixin, forms.ModelForm):
    class Meta:
        model = PropostaTributo
        exclude = ["revisao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class MotivoStatusForm(ClasseCssMixin, forms.Form):
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 4}), min_length=3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class AcompanhamentoPropostaForm(ClasseCssMixin, forms.ModelForm):
    class Meta:
        model = HistoricoContatoProposta
        fields = ["descricao", "proxima_acao", "data_retorno"]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 4}), "data_retorno": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class RelatorioPropostasFiltroForm(ClasseCssMixin, forms.Form):
    empresa = forms.ModelChoiceField(Empresa.objects.filter(ativa=True), required=True)
    data_inicial = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date"}))
    data_final = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date"}))
    numero = forms.CharField(required=False)
    cliente = forms.ModelChoiceField(Pessoa.objects.filter(ativo=True), required=False)
    contato = forms.CharField(required=False)
    responsavel = forms.ModelChoiceField(get_user_model().objects.all(), required=False)
    status = forms.ChoiceField(choices=[("","Todos")]+list(Proposta.Status.choices), required=False)
    busca = forms.CharField(required=False)

    def __init__(self,*args,usuario=None,**kwargs):
        super().__init__(*args,**kwargs)
        if usuario is not None:
            self.fields["empresa"].queryset = empresas_usuario(usuario, ativas=True)
        self.aplicar_classes()

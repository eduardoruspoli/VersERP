from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from financeiro.models import Empresa
from financeiro.models import PlanoConta
from pessoas.models import Pessoa

from .models import Proposta, PropostaItem, PropostaLinhaPublica, PropostaRevisao, PropostaTributo


class ClasseCssMixin:
    def aplicar_classes(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-select" if isinstance(field.widget, forms.Select) else "form-control")


class PropostaCriacaoForm(ClasseCssMixin, forms.Form):
    empresa = forms.ModelChoiceField(Empresa.objects.filter(ativa=True))
    codigo = forms.CharField(label="Número da proposta", max_length=20, help_text="Ex.: VERS1917")
    cliente = forms.ModelChoiceField(Pessoa.objects.filter(ativo=True).filter(Q(classificacao="CLIENTE") | Q(classificacao="AMBOS")))
    nome_servico = forms.CharField(max_length=250)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    class Meta:
        model = PropostaRevisao
        exclude = ["proposta", "numero", "modelo_conteudo", "congelada", "enviada_em", "criado_por", "criado_em", "empresa_nome_snapshot", "empresa_documento_snapshot", "cliente_nome_snapshot", "cliente_documento_snapshot"]
        widgets = {campo: forms.Textarea(attrs={"rows": 3}) for campo in ("escopo_incluido", "nao_incluso", "texto_introdutorio", "normas_procedimentos", "qualificacao_mao_obra", "obrigacoes_contratada", "observacoes_comerciais", "condicao_pagamento", "observacoes_internas")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class PropostaItemForm(ClasseCssMixin, forms.ModelForm):
    class Meta:
        model = PropostaItem
        exclude = ["revisao", "custo_total"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()
        self.fields["fornecedor"].queryset = Pessoa.objects.filter(ativo=True).filter(Q(classificacao="FORNECEDOR") | Q(classificacao="AMBOS"))
        self.fields["plano_conta"].queryset = PlanoConta.objects.filter(ativo=True, estrutural=False, aceita_lancamento=True, tipo__in=("CUSTO", "DESPESA"))


class PropostaLinhaPublicaForm(ClasseCssMixin, forms.ModelForm):
    class Meta:
        model = PropostaLinhaPublica
        exclude = ["revisao"]

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

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.aplicar_classes()

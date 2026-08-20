from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from comercial.models import Proposta, PropostaItem
from financeiro.models import CentroCusto, Empresa, PlanoConta
from pessoas.models import Pessoa

from .models import (CotacaoFornecedor, CotacaoFornecedorItem, ProcessoCotacao,
                     DivergenciaDocumentoCompra, DivergenciaRecebimento, DocumentoCompra,
                     DocumentoCompraItem, DocumentoCompraItemRecebimento, DocumentoCompraPedido,
                     DocumentoCompraParcela,
                     ProcessoCotacaoItem, PedidoCompra, PedidoCompraItem,
                     PedidoItemAlocacaoObra, RecebimentoCompra, RecebimentoCompraItem,
                     SolicitacaoCompra, SolicitacaoCompraItem)


class SolicitacaoCompraForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoCompra
        fields = ["empresa", "obra", "data_solicitacao", "prioridade", "observacao"]
        widgets = {
            "empresa": forms.Select(attrs={"class": "form-select"}),
            "obra": forms.Select(attrs={"class": "form-select"}),
            "data_solicitacao": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "prioridade": forms.Select(attrs={"class": "form-select"}),
            "observacao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True)
        empresa_id = self.data.get("empresa") or getattr(self.instance, "empresa_id", None)
        obras = CentroCusto.objects.filter(ativo=True)
        self.fields["obra"].queryset = (obras.filter(empresa_id=empresa_id) if empresa_id else obras).select_related("empresa").order_by("empresa", "codigo")
        if self.instance.pk and self.instance.status != SolicitacaoCompra.Status.RASCUNHO:
            self.fields["empresa"].disabled = True
            self.fields["obra"].disabled = True


class SolicitacaoCompraItemForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoCompraItem
        fields = ["proposta_item", "tipo_origem", "descricao", "quantidade", "unidade", "data_necessaria", "descricao_item_substituido", "observacao", "cancelado"]
        widgets = {
            "proposta_item": forms.Select(attrs={"class": "form-select item-previsto"}),
            "tipo_origem": forms.Select(attrs={"class": "form-select tipo-origem"}),
            "descricao": forms.TextInput(attrs={"class": "form-control descricao-item"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}),
            "unidade": forms.TextInput(attrs={"class": "form-control"}),
            "data_necessaria": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "descricao_item_substituido": forms.TextInput(attrs={"class": "form-control"}),
            "observacao": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "cancelado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        obra = kwargs.pop("obra", None)
        super().__init__(*args, **kwargs)
        queryset = PropostaItem.objects.none()
        if obra and hasattr(obra, "proposta_origem") and obra.proposta_origem.revisao_aprovada_id:
            queryset = PropostaItem.objects.filter(revisao_id=obra.proposta_origem.revisao_aprovada_id).order_by("ordem", "id")
        elif self.instance.pk and self.instance.proposta_item_id:
            queryset = PropostaItem.objects.filter(pk=self.instance.proposta_item_id)
        self.fields["proposta_item"].queryset = queryset
        self.fields["proposta_item"].required = False
        self.fields["proposta_item"].empty_label = "Item não previsto / selecionar item aprovado"


class BaseSolicitacaoItemFormSet(BaseInlineFormSet):
    def __init__(self, *args, obra=None, **kwargs):
        self.obra = obra
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["obra"] = self.obra
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        ativos = 0
        previstos = set()
        for form in self.forms:
            dados = form.cleaned_data
            if not dados or dados.get("DELETE") or dados.get("cancelado"):
                continue
            ativos += 1
            item = dados.get("proposta_item")
            if item and item.pk in previstos:
                raise forms.ValidationError("O mesmo item previsto não pode aparecer duas vezes na solicitação.")
            if item:
                previstos.add(item.pk)
        if not ativos:
            raise forms.ValidationError("Inclua ao menos um item ativo na solicitação.")


SolicitacaoCompraItemFormSet = inlineformset_factory(
    SolicitacaoCompra,
    SolicitacaoCompraItem,
    form=SolicitacaoCompraItemForm,
    formset=BaseSolicitacaoItemFormSet,
    extra=1,
    can_delete=True,
)


class MotivoCancelamentoForm(forms.Form):
    motivo = forms.CharField(label="Motivo do cancelamento", min_length=3, widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}))


class ProcessoCotacaoForm(forms.ModelForm):
    itens_solicitacao = forms.ModelMultipleChoiceField(queryset=SolicitacaoCompraItem.objects.none(), label="Itens de solicitações abertas", widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = ProcessoCotacao
        fields = ["empresa", "responsavel", "data_abertura", "data_limite", "observacao"]
        widgets = {"empresa": forms.Select(attrs={"class":"form-select"}), "responsavel": forms.Select(attrs={"class":"form-select"}), "data_abertura": forms.DateInput(attrs={"class":"form-control","type":"date"}), "data_limite": forms.DateInput(attrs={"class":"form-control","type":"date"}), "observacao": forms.Textarea(attrs={"class":"form-control","rows":3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = self.data.get("empresa") or getattr(self.instance, "empresa_id", None)
        qs = SolicitacaoCompraItem.objects.filter(cancelado=False, solicitacao__status__in=[SolicitacaoCompra.Status.ABERTA, SolicitacaoCompra.Status.EM_COTACAO]).select_related("solicitacao__obra")
        if empresa_id: qs = qs.filter(solicitacao__empresa_id=empresa_id)
        self.fields["itens_solicitacao"].queryset = qs


class CotacaoFornecedorForm(forms.ModelForm):
    class Meta:
        model = CotacaoFornecedor
        exclude = ["processo", "registrada_por"]
        widgets = {name: forms.TextInput(attrs={"class":"form-control"}) for name in ["nome_contato","telefone","email","prazo_entrega","tipo_frete","disponibilidade"]}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = Pessoa.objects.filter(ativo=True, classificacao__in=[Pessoa.Classificacao.FORNECEDOR, Pessoa.Classificacao.AMBOS])
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-select" if isinstance(field.widget, forms.Select) else "form-control")


class CotacaoFornecedorItemForm(forms.ModelForm):
    class Meta:
        model = CotacaoFornecedorItem
        exclude = ["cotacao", "preco_total"]
    def __init__(self, *args, cotacao=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cotacao: self.fields["processo_item"].queryset = cotacao.processo.itens.all()
        for field in self.fields.values(): field.widget.attrs.setdefault("class", "form-select" if isinstance(field.widget, forms.Select) else "form-control")


class EscolhaOfertaForm(forms.Form):
    oferta = forms.IntegerField(widget=forms.HiddenInput)
    justificativa = forms.CharField(required=False, widget=forms.Textarea(attrs={"class":"form-control","rows":2}))
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"class":"form-control","rows":2}))


class PedidoCompraForm(forms.ModelForm):
    class Meta:
        model=PedidoCompra
        fields=["empresa","fornecedor","origem","justificativa_origem","numero_pedido_versatile","numero_pedido_fornecedor","data_pedido","nome_vendedor_fornecedor_snapshot","telefone_vendedor_snapshot","email_vendedor_snapshot","condicao_pagamento","prazo_entrega","tipo_frete","transportadora","transportadora_nome_snapshot","transportadora_documento_snapshot","transportadora_contato_snapshot","dados_bancarios","instrucoes_entrega","observacoes","frete","desconto","impostos","outras_despesas","responsavel_nome_snapshot","responsavel_cargo_snapshot","assinatura_textual"]
        widgets={"data_pedido":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not self.instance.pk: self.fields["origem"].choices=[(PedidoCompra.Origem.DIRETA,"Direta"),(PedidoCompra.Origem.EMERGENCIAL,"Emergencial")]
        self.fields["empresa"].queryset=Empresa.objects.filter(ativa=True)
        self.fields["fornecedor"].queryset=Pessoa.objects.filter(ativo=True,classificacao__in=[Pessoa.Classificacao.FORNECEDOR,Pessoa.Classificacao.AMBOS])
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,(forms.Select,forms.SelectMultiple)) else "form-control")


class PedidoCompraItemForm(forms.ModelForm):
    class Meta:
        model=PedidoCompraItem
        fields=["solicitacao_item","proposta_item","proposta_codigo_snapshot","descricao_mercadoria","quantidade","unidade","valor_unitario","plano_conta","observacao","ordem"]
    def __init__(self,*args,pedido=None,**kwargs):
        super().__init__(*args,**kwargs)
        if pedido: self.fields["solicitacao_item"].queryset=SolicitacaoCompraItem.objects.filter(solicitacao__empresa=pedido.empresa,cancelado=False)
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class PedidoItemAlocacaoForm(forms.ModelForm):
    class Meta:
        model=PedidoItemAlocacaoObra
        fields=["obra","solicitacao_item","proposta_item","quantidade","valor","tipo_origem","observacao"]
    def __init__(self,*args,pedido_item=None,**kwargs):
        super().__init__(*args,**kwargs)
        if pedido_item:
            self.fields["obra"].queryset=CentroCusto.objects.filter(empresa=pedido_item.pedido.empresa,ativo=True)
            self.fields["solicitacao_item"].queryset=SolicitacaoCompraItem.objects.filter(solicitacao__empresa=pedido_item.pedido.empresa)
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class GerarPedidosCotacaoForm(forms.Form):
    def __init__(self,*args,processo=None,**kwargs):
        super().__init__(*args,**kwargs)
        ids=processo.itens.filter(escolha__isnull=False).values_list("escolha__oferta_escolhida__cotacao__fornecedor_id",flat=True).distinct()
        for fornecedor in Pessoa.objects.filter(pk__in=ids):
            self.fields[f"fornecedor_{fornecedor.pk}"]=forms.CharField(label=f"Nº Pedido Versatile — {fornecedor}",widget=forms.TextInput(attrs={"class":"form-control"}))


class RecebimentoCompraForm(forms.ModelForm):
    class Meta:
        model=RecebimentoCompra
        fields=["data_recebimento","responsavel","numero_documento","observacao"]
        widgets={"data_recebimento":forms.DateInput(attrs={"class":"form-control","type":"date"}),"responsavel":forms.Select(attrs={"class":"form-select"}),"numero_documento":forms.TextInput(attrs={"class":"form-control"}),"observacao":forms.Textarea(attrs={"class":"form-control","rows":3})}


class RecebimentoCompraItemForm(forms.ModelForm):
    class Meta:
        model=RecebimentoCompraItem
        fields=["pedido_item","quantidade_recebida","quantidade_aceita","quantidade_rejeitada","observacao"]
    def __init__(self,*args,pedido=None,**kwargs):
        super().__init__(*args,**kwargs)
        if pedido: self.fields["pedido_item"].queryset=pedido.itens.all()
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class BaseRecebimentoItemFormSet(BaseInlineFormSet):
    def __init__(self,*args,pedido=None,**kwargs): self.pedido=pedido; super().__init__(*args,**kwargs)
    def get_form_kwargs(self,index): kwargs=super().get_form_kwargs(index); kwargs["pedido"]=self.pedido; return kwargs

RecebimentoCompraItemFormSet=inlineformset_factory(RecebimentoCompra,RecebimentoCompraItem,form=RecebimentoCompraItemForm,formset=BaseRecebimentoItemFormSet,extra=1,can_delete=True)


class DivergenciaRecebimentoForm(forms.ModelForm):
    class Meta:
        model=DivergenciaRecebimento
        fields=["tipo","descricao","quantidade_afetada"]
        widgets={"tipo":forms.Select(attrs={"class":"form-select"}),"descricao":forms.Textarea(attrs={"class":"form-control","rows":3}),"quantidade_afetada":forms.NumberInput(attrs={"class":"form-control","step":"0.0001"})}

class SolucaoDivergenciaForm(forms.Form):
    solucao=forms.CharField(widget=forms.Textarea(attrs={"class":"form-control","rows":3}))


class PrevistoCompradoFiltroForm(forms.Form):
    empresa=forms.ModelChoiceField(queryset=Empresa.objects.all(),required=True,widget=forms.Select(attrs={"class":"form-select"}))
    obra=forms.ModelChoiceField(queryset=CentroCusto.objects.all(),required=True,widget=forms.Select(attrs={"class":"form-select"}))
    proposta=forms.ModelChoiceField(queryset=Proposta.objects.all(),required=False,widget=forms.Select(attrs={"class":"form-select"}))
    tipo_origem=forms.ChoiceField(choices=[("","Todas as origens")]+list(SolicitacaoCompraItem.TipoOrigem.choices),required=False,widget=forms.Select(attrs={"class":"form-select"}))
    status=forms.ChoiceField(choices=[("","Todos os pedidos")]+list(PedidoCompra.Status.choices),required=False,widget=forms.Select(attrs={"class":"form-select"}))
    plano_conta=forms.ModelChoiceField(queryset=PlanoConta.objects.all(),required=False,widget=forms.Select(attrs={"class":"form-select"}))
    somente_divergencias=forms.BooleanField(required=False,widget=forms.CheckboxInput(attrs={"class":"form-check-input"}))
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); empresa_id=self.data.get("empresa") or self.initial.get("empresa")
        if empresa_id:
            self.fields["obra"].queryset=CentroCusto.objects.filter(empresa_id=empresa_id).order_by("codigo")
            self.fields["proposta"].queryset=Proposta.objects.filter(empresa_id=empresa_id,revisao_aprovada__isnull=False)
            self.fields["plano_conta"].queryset=PlanoConta.objects.filter(empresa_id=empresa_id) if hasattr(PlanoConta,"empresa_id") else PlanoConta.objects.all()


class DocumentoCompraForm(forms.ModelForm):
    class Meta:
        model=DocumentoCompra
        fields=["empresa","fornecedor","tipo","numero","serie","chave_fiscal","data_emissao","data_entrada","valor_bruto","desconto","frete","impostos","outras_despesas","condicao_pagamento","observacoes"]
        widgets={"data_emissao":forms.DateInput(attrs={"type":"date"}),"data_entrada":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.fields["empresa"].queryset=Empresa.objects.filter(ativa=True); self.fields["fornecedor"].queryset=Pessoa.objects.filter(ativo=True,classificacao__in=[Pessoa.Classificacao.FORNECEDOR,Pessoa.Classificacao.AMBOS])
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class DocumentoCompraItemForm(forms.ModelForm):
    class Meta:
        model=DocumentoCompraItem
        fields=["pedido_item","descricao_snapshot","quantidade_faturada","unidade","valor_unitario_faturado","desconto","frete_alocado","impostos","outras_despesas","plano_conta","observacao","ordem"]
    def __init__(self,*args,documento=None,**kwargs):
        super().__init__(*args,**kwargs)
        if documento: self.fields["pedido_item"].queryset=PedidoCompraItem.objects.filter(pedido__empresa=documento.empresa,pedido__fornecedor=documento.fornecedor).select_related("pedido")
        self.fields["plano_conta"].queryset=PlanoConta.objects.filter(ativo=True,estrutural=False,aceita_lancamento=True,tipo__in=["CUSTO","DESPESA"])
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class DocumentoCompraPedidoForm(forms.ModelForm):
    class Meta: model=DocumentoCompraPedido; fields=["pedido"]
    def __init__(self,*args,documento=None,**kwargs):
        super().__init__(*args,**kwargs)
        if documento: self.fields["pedido"].queryset=PedidoCompra.objects.filter(empresa=documento.empresa,fornecedor=documento.fornecedor).exclude(status__in=[PedidoCompra.Status.RASCUNHO,PedidoCompra.Status.AGUARDANDO_APROVACAO,PedidoCompra.Status.REJEITADO,PedidoCompra.Status.CANCELADO])
        self.fields["pedido"].widget.attrs["class"]="form-select"


class DocumentoItemRecebimentoForm(forms.ModelForm):
    class Meta: model=DocumentoCompraItemRecebimento; fields=["recebimento_item","quantidade_vinculada"]
    def __init__(self,*args,documento_item=None,**kwargs):
        super().__init__(*args,**kwargs)
        qs=RecebimentoCompraItem.objects.filter(recebimento__status=RecebimentoCompra.Status.CONFIRMADO)
        if documento_item:
            qs=qs.filter(recebimento__pedido__empresa=documento_item.documento.empresa,recebimento__pedido__fornecedor=documento_item.documento.fornecedor)
            if documento_item.pedido_item_id: qs=qs.filter(pedido_item=documento_item.pedido_item)
        self.fields["recebimento_item"].queryset=qs.select_related("recebimento","pedido_item")
        self.fields["recebimento_item"].widget.attrs["class"]="form-select"; self.fields["quantidade_vinculada"].widget.attrs.update({"class":"form-control","step":"0.0001"})


class DivergenciaDocumentoForm(forms.ModelForm):
    class Meta:
        model=DivergenciaDocumentoCompra
        fields=["documento_item","tipo","descricao","quantidade_afetada","valor_afetado","bloqueante"]
    def __init__(self,*args,documento=None,**kwargs):
        super().__init__(*args,**kwargs)
        if documento: self.fields["documento_item"].queryset=documento.itens.all()
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-select" if isinstance(field.widget,forms.Select) else "form-control")


class SolucaoDivergenciaDocumentoForm(forms.Form):
    solucao=forms.CharField(widget=forms.Textarea(attrs={"class":"form-control","rows":3}))


class DocumentoCompraParcelaForm(forms.ModelForm):
    class Meta:
        model=DocumentoCompraParcela
        fields=["numero","vencimento","valor","observacao"]
        widgets={"vencimento":forms.DateInput(attrs={"class":"form-control","type":"date"}),"observacao":forms.Textarea(attrs={"class":"form-control","rows":2})}
    def __init__(self,*args,documento=None,**kwargs):
        super().__init__(*args,**kwargs); self.documento=documento or getattr(self.instance,"documento",None)
        for field in self.fields.values(): field.widget.attrs.setdefault("class","form-control")
    def clean(self):
        dados=super().clean()
        if self.documento and self.documento.parcelas.filter(parcela_financeira__isnull=False).exclude(pk=self.instance.pk).exists(): raise ValidationError("As parcelas integradas ao Financeiro estão congeladas.")
        return dados


class GerarParcelasDocumentoForm(forms.Form):
    tipo=forms.ChoiceField(label="Condição",choices=[("VISTA","À vista"),("30","30 dias"),("30_60","30/60 dias"),("30_60_90","30/60/90 dias"),("IGUAIS","Parcelas iguais")],widget=forms.Select(attrs={"class":"form-select"}))
    quantidade=forms.IntegerField(label="Quantidade",required=False,min_value=1,max_value=120,widget=forms.NumberInput(attrs={"class":"form-control","min":1}))
    primeiro_vencimento_dias=forms.IntegerField(label="Primeiro vencimento (dias)",required=False,min_value=0,initial=30,widget=forms.NumberInput(attrs={"class":"form-control","min":0}))
    intervalo_dias=forms.IntegerField(label="Intervalo (dias)",required=False,min_value=1,initial=30,widget=forms.NumberInput(attrs={"class":"form-control","min":1}))
    def clean(self):
        dados=super().clean(); tipo=dados.get("tipo")
        mapa={"VISTA":(1,0),"30":(1,30),"30_60":(2,30),"30_60_90":(3,30)}
        if tipo in mapa: dados["quantidade"],dados["primeiro_vencimento_dias"]=mapa[tipo]; dados["intervalo_dias"]=30
        elif not dados.get("quantidade"): self.add_error("quantidade","Informe a quantidade de parcelas.")
        return dados

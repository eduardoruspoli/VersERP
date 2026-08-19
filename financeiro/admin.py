from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet


from .models import (
    BaixaFinanceira,
    CentroCusto,
    ContaBancaria,
    Empresa,
    LancamentoFinanceiro,
    LancamentoFinanceiroClassificacao,
    ParcelaFinanceira,
    PlanoConta,
    RateioCentroCusto,
)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = (
        "razao_social",
        "nome_fantasia",
        "cnpj",
        "ativa",
        "principal",
    )

    search_fields = (
        "razao_social",
        "nome_fantasia",
        "cnpj",
    )

    list_filter = (
        "ativa",
        "principal",
    )


@admin.register(ContaBancaria)
class ContaBancariaAdmin(admin.ModelAdmin):
    list_display = (
        "empresa",
        "banco",
        "agencia",
        "conta",
        "tipo",
        "saldo_inicial",
        "ativa",
    )

    list_filter = (
        "empresa",
        "tipo",
        "ativa",
    )

    search_fields = (
        "banco",
        "codigo_banco",
        "agencia",
        "conta",
        "descricao",
    )


@admin.register(PlanoConta)
class PlanoContaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "nome",
        "tipo",
        "natureza",
        "conta_redutora",
        "conta_pai",
        "aceita_lancamento",
        "ativo",
    )

    list_filter = (
        "tipo",
        "natureza",
        "conta_redutora",
        "aceita_lancamento",
        "ativo",
    )

    search_fields = (
        "codigo",
        "nome",
    )


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = (
        "empresa",
        "codigo",
        "nome",
        "cliente",
        "ativo",
    )

    list_filter = (
        "empresa",
        "ativo",
    )

    search_fields = (
        "codigo",
        "nome",
        "cliente__razao_social",
    )

class ParcelaFinanceiraInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        total_parcelas = 0

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            valor = form.cleaned_data.get("valor")

            if valor is not None:
                total_parcelas += valor

        if self.instance.valor_total is None:
            return

        if total_parcelas != self.instance.valor_total:
            raise ValidationError(
                "A soma das parcelas deve ser igual ao valor total "
                f"do lançamento (R$ {self.instance.valor_total:.2f}). "
                f"Total informado: R$ {total_parcelas:.2f}."
            )

class ParcelaFinanceiraInline(admin.TabularInline):
    model = ParcelaFinanceira
    extra = 0
    formset = ParcelaFinanceiraInlineFormSet

    fields = (
        "numero",
        "vencimento",
        "valor",
        "status",
    )


class RateioCentroCustoInline(admin.TabularInline):
    model = RateioCentroCusto
    extra = 0

    fields = (
        "centro_custo",
        "valor",
    )


class LancamentoFinanceiroClassificacaoInline(admin.TabularInline):
    model = LancamentoFinanceiroClassificacao
    extra = 0
    fields = ("plano_conta", "valor", "observacao", "ordem")

    class FormSet(BaseInlineFormSet):
        def clean(self):
            super().clean()
            if any(self.errors): return
            dados=[]
            for form in self.forms:
                if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                    dados.append({campo:form.cleaned_data.get(campo) for campo in ("plano_conta","valor","observacao","ordem")})
            contas=[item["plano_conta"] for item in dados]
            if len(contas)!=len(set(contas)): raise ValidationError("Não repita a mesma conta contábil.")
            if sum((item["valor"] for item in dados),0)!=self.instance.valor_total: raise ValidationError("As classificações devem fechar com o valor total.")

        def save(self, commit=True):
            from .services import salvar_classificacoes_lancamento
            dados=[]
            for form in self.forms:
                if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                    dados.append({campo:form.cleaned_data.get(campo) for campo in ("plano_conta","valor","observacao","ordem")})
            return salvar_classificacoes_lancamento(self.instance,dados) if commit else []

    formset = FormSet

    def has_change_permission(self, request, obj=None):
        if obj and obj.parcelas.filter(baixas__isnull=False).exists():
            return False
        return request.user.has_perm("financeiro.change_classificacoes_multiplas")

    has_add_permission = has_change_permission
    has_delete_permission = has_change_permission


@admin.register(LancamentoFinanceiro)
class LancamentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "tipo",
        "empresa",
        "pessoa",
        "valor_total",
        "status",
        "data_emissao",
        "origem",
    )

    list_filter = (
        "tipo",
        "status",
        "origem",
        "empresa",
        "plano_conta",
    )

    search_fields = (
        "descricao",
        "numero_documento",
        "pessoa__razao_social",
        "pessoa__nome_fantasia",
    )

    autocomplete_fields = (
        "empresa",
        "pessoa",
        "plano_conta",
    )

    inlines = [
        LancamentoFinanceiroClassificacaoInline,
        ParcelaFinanceiraInline,
        RateioCentroCustoInline,
    ]


class BaixaFinanceiraInline(admin.TabularInline):
    model = BaixaFinanceira
    extra = 0

    fields = (
        "conta_bancaria",
        "data",
        "valor",
        "juros",
        "multa",
        "desconto",
    )


@admin.register(ParcelaFinanceira)
class ParcelaFinanceiraAdmin(admin.ModelAdmin):
    list_display = (
        "lancamento",
        "numero",
        "vencimento",
        "valor",
        "exibir_total_baixado",
        "exibir_saldo",
        "status",
    )

    list_filter = (
        "status",
        "vencimento",
    )

    search_fields = (
        "lancamento__descricao",
        "lancamento__numero_documento",
    )

    autocomplete_fields = (
        "lancamento",
    )

    readonly_fields = (
        "exibir_total_baixado",
        "exibir_saldo",
    )

    inlines = [
        BaixaFinanceiraInline,
    ]

    @admin.display(description="Total baixado")
    def exibir_total_baixado(self, obj):
        return f"R$ {obj.total_baixado:.2f}"

    @admin.display(description="Saldo")
    def exibir_saldo(self, obj):
        return f"R$ {obj.saldo:.2f}"

@admin.register(BaixaFinanceira)
class BaixaFinanceiraAdmin(admin.ModelAdmin):
    list_display = (
        "parcela",
        "conta_bancaria",
        "data",
        "valor",
        "juros",
        "multa",
        "desconto",
    )

    list_filter = (
        "data",
        "conta_bancaria",
    )

    search_fields = (
        "parcela__lancamento__descricao",
        "parcela__lancamento__numero_documento",
    )


@admin.register(RateioCentroCusto)
class RateioCentroCustoAdmin(admin.ModelAdmin):
    list_display = (
        "lancamento",
        "centro_custo",
        "valor",
    )

    list_filter = (
        "centro_custo",
    )

    search_fields = (
        "lancamento__descricao",
        "centro_custo__codigo",
        "centro_custo__nome",
    )

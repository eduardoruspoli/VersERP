from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

from financeiro.models import Empresa

from .access import empresas_usuario


class UsuarioAdministracaoForm(forms.ModelForm):
    grupos = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    empresas = forms.ModelMultipleChoiceField(queryset=Empresa.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, ator=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ator and not ator.is_superuser:
            permissoes_ator = set(ator.get_all_permissions())
            grupos_permitidos = []
            for grupo in Group.objects.prefetch_related("permissions__content_type"):
                permissoes_grupo = {
                    f"{permissao.content_type.app_label}.{permissao.codename}"
                    for permissao in grupo.permissions.all()
                }
                if permissoes_grupo.issubset(permissoes_ator):
                    grupos_permitidos.append(grupo.pk)
            self.fields["grupos"].queryset = Group.objects.filter(pk__in=grupos_permitidos)
            self.fields["empresas"].queryset = empresas_usuario(ator)
        if self.instance.pk:
            self.fields["grupos"].initial = self.instance.groups.all()
            self.fields["empresas"].initial = empresas_usuario(self.instance)
        for campo in self.fields.values():
            if not isinstance(campo.widget, forms.CheckboxSelectMultiple):
                campo.widget.attrs.setdefault("class", "form-control")


class GrupoForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {"permissions": forms.CheckboxSelectMultiple}

    def __init__(self, *args, ator=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ator and not ator.is_superuser:
            filtro = Q(pk__in=[])
            for permissao in ator.get_all_permissions():
                app_label, codename = permissao.split(".", 1)
                filtro |= Q(content_type__app_label=app_label, codename=codename)
            self.fields["permissions"].queryset = Permission.objects.filter(filtro)
        self.fields["name"].widget.attrs["class"] = "form-control"

class EmpresaConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["razao_social", "nome_fantasia", "cnpj", "endereco", "numero", "complemento", "bairro", "cidade", "estado", "cep", "inscricao_estadual", "inscricao_municipal", "email", "telefone", "ativa", "principal"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-check-input" if isinstance(campo.widget, forms.CheckboxInput) else "form-control")


class FeriadoConfiguracaoForm(forms.ModelForm):
    class Meta:
        from rh.models import Feriado
        model = Feriado
        fields = ["empresa", "data", "nome", "localidade"]
        widgets = {"data": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["empresa"].queryset = empresas_usuario(usuario, ativas=True)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-select" if isinstance(campo.widget, forms.Select) else "form-control")


class ModeloPropostaConfiguracaoForm(forms.ModelForm):
    class Meta:
        from comercial.models import ModeloConteudoProposta
        model = ModeloConteudoProposta
        fields = ["empresa", "nome", "ativo", "padrao", "texto_introdutorio", "normas_procedimentos", "qualificacao_mao_obra", "obrigacoes_contratada", "observacoes_comerciais", "observacao_faturamento", "texto_impostos", "multa_juros_atraso", "regra_protesto", "rodape"]
        widgets = {campo: forms.Textarea(attrs={"rows": 4}) for campo in ["texto_introdutorio", "normas_procedimentos", "qualificacao_mao_obra", "obrigacoes_contratada", "observacoes_comerciais", "observacao_faturamento", "texto_impostos", "multa_juros_atraso", "regra_protesto", "rodape"]}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["empresa"].queryset = empresas_usuario(usuario, ativas=True)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-check-input" if isinstance(campo.widget, forms.CheckboxInput) else "form-select" if isinstance(campo.widget, forms.Select) else "form-control")

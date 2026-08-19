from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from financeiro.models import Empresa

from .access import empresas_usuario


class UsuarioAdministracaoForm(forms.ModelForm):
    grupos = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    empresas = forms.ModelMultipleChoiceField(queryset=Empresa.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "form-control"

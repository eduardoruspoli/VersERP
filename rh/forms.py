from django import forms

from financeiro.models import Empresa
from pessoas.models import Pessoa

from .models import (CompetenciaPonto, ConferenciaFolha, ContratoFuncionario,
                     EventoFolha, Funcionario, Jornada, JornadaDia,
                     MarcacaoPonto, OcorrenciaPonto, RetornoContabilidade,
                     ValeAdiantamento)


class EstiloFormMixin:
    def aplicar_estilo(self):
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-select" if isinstance(campo.widget, (forms.Select, forms.SelectMultiple)) else "form-control")


class FuncionarioForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = ["empresa", "pessoa", "matricula", "nome_apresentacao", "cargo_atual", "data_admissao", "data_desligamento", "situacao", "observacoes"]
        labels = {"matricula":"Matrícula", "nome_apresentacao":"Nome de apresentação", "cargo_atual":"Cargo atual", "data_admissao":"Data de admissão", "data_desligamento":"Data de desligamento", "situacao":"Situação", "observacoes":"Observações"}
        widgets = {"data_admissao": forms.DateInput(attrs={"type":"date"}), "data_desligamento": forms.DateInput(attrs={"type":"date"}), "observacoes": forms.Textarea(attrs={"rows":3})}
    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True)
        self.fields["pessoa"].queryset = Pessoa.objects.filter(ativo=True, tipo_pessoa=Pessoa.TipoPessoa.FISICA)
        if empresa:
            self.fields["empresa"].queryset = Empresa.objects.filter(pk=empresa.pk)
        self.aplicar_estilo()


class DadosBancariosForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = ["banco", "agencia", "conta", "chave_pix"]
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class ContratoForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = ContratoFuncionario
        fields = ["inicio_vigencia", "fim_vigencia", "salario_base", "divisor_salarial", "carga_semanal_minutos", "cargo", "observacao"]
        widgets = {"inicio_vigencia":forms.DateInput(attrs={"type":"date"}), "fim_vigencia":forms.DateInput(attrs={"type":"date"}), "observacao":forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class JornadaForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=Jornada; fields=["nome","inicio_vigencia","fim_vigencia","observacao"]
        widgets={"inicio_vigencia":forms.DateInput(attrs={"type":"date"}),"fim_vigencia":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class JornadaDiaForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=JornadaDia; fields=["dia_semana","trabalha","entrada","saida_intervalo","retorno_intervalo","saida","minutos_previstos"]
        widgets={nome:forms.TimeInput(attrs={"type":"time"}) for nome in ["entrada","saida_intervalo","retorno_intervalo","saida"]}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class CompetenciaForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=CompetenciaPonto; fields=["funcionario","competencia","ajustes_minutos","observacoes"]
        widgets={"competencia":forms.DateInput(attrs={"type":"date"}),"observacoes":forms.Textarea(attrs={"rows":2})}
    def __init__(self,*args,empresa=None,**kwargs):
        super().__init__(*args,**kwargs)
        if empresa: self.fields["funcionario"].queryset=Funcionario.objects.filter(empresa=empresa)
        self.aplicar_estilo()


class MarcacaoForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=MarcacaoPonto; fields=["data","horario","origem","observacao","substitui"]
        widgets={"data":forms.DateInput(attrs={"type":"date"}),"horario":forms.TimeInput(attrs={"type":"time"})}
    def __init__(self,*args,funcionario=None,**kwargs):
        super().__init__(*args,**kwargs)
        if funcionario: self.fields["substitui"].queryset=funcionario.marcacoes.filter(ativa=True)
        self.aplicar_estilo()


class OcorrenciaForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=OcorrenciaPonto; fields=["data_inicio","data_fim","tipo","descricao","minutos_abonados","observacao"]
        widgets={"data_inicio":forms.DateInput(attrs={"type":"date"}),"data_fim":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class EventoForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=EventoFolha; fields=["funcionario","competencia","data_evento","tipo","descricao","natureza","quantidade","unidade","valor","observacao"]
        widgets={"competencia":forms.DateInput(attrs={"type":"date"}),"data_evento":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,empresa=None,**kwargs):
        super().__init__(*args,**kwargs)
        if empresa: self.fields["funcionario"].queryset=Funcionario.objects.filter(empresa=empresa)
        self.aplicar_estilo()


class ValeForm(EstiloFormMixin, forms.ModelForm):
    competencia_inicial=forms.DateField(widget=forms.DateInput(attrs={"type":"date","class":"form-control"}))
    class Meta:
        model=ValeAdiantamento; fields=["funcionario","data","descricao","valor_total","quantidade_parcelas"]
        widgets={"data":forms.DateInput(attrs={"type":"date"})}
    def __init__(self,*args,empresa=None,**kwargs):
        super().__init__(*args,**kwargs)
        if empresa: self.fields["funcionario"].queryset=Funcionario.objects.filter(empresa=empresa)
        self.aplicar_estilo()


class RetornoForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=RetornoContabilidade; exclude=["registrado_por"]
        widgets={"competencia":forms.DateInput(attrs={"type":"date"}),"observacao":forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,empresa=None,**kwargs):
        super().__init__(*args,**kwargs)
        if empresa: self.fields["funcionario"].queryset=Funcionario.objects.filter(empresa=empresa)
        self.aplicar_estilo()


class ConferenciaForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=ConferenciaFolha; fields=["status","justificativa"]
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilo()


class MotivoForm(forms.Form):
    motivo=forms.CharField(min_length=3,widget=forms.Textarea(attrs={"class":"form-control","rows":3}))

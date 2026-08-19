from django.core.exceptions import PermissionDenied
from django.apps import apps

from .access import pode_acessar_empresa


class EmpresaAccessMiddleware:
    """Bloqueia seleção explícita de empresa fora do escopo do usuário.

    A filtragem dos objetos permanece responsabilidade das views/services. Esta
    barreira cobre parâmetros GET/POST manipulados antes que forms sejam salvos.
    """

    PARAMETROS = ("empresa", "empresa_id")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            # GETs são resolvidos pelos querysets autorizados (404, sem revelar
            # existência). POSTs recebem uma barreira adicional antes do form.
            for origem in (request.POST,):
                empresa_id = next((origem.get(nome) for nome in self.PARAMETROS if origem.get(nome)), None)
                if empresa_id and str(empresa_id).isdigit() and not pode_acessar_empresa(request.user, empresa_id):
                    raise PermissionDenied("Empresa não autorizada para este usuário.")
        return self.get_response(request)

    ROTAS = {
        "comercial": {
            "proposta": ("comercial.Proposta", "empresa_id"),
            "revisao": ("comercial.PropostaRevisao", "proposta__empresa_id"),
        },
        "compras": {
            "solicitacao": ("compras.SolicitacaoCompra", "empresa_id"),
            "cotacao": ("compras.ProcessoCotacao", "empresa_id"),
            "pedido": ("compras.PedidoCompra", "empresa_id"),
            "recebimento": ("compras.RecebimentoCompra", "pedido__empresa_id"),
            "documento": ("compras.DocumentoCompra", "empresa_id"),
            "divergencia": ("compras.DivergenciaRecebimento", "recebimento_item__recebimento__pedido__empresa_id"),
        },
        "rh": {
            "funcionario": ("rh.Funcionario", "empresa_id"),
            "competencia": ("rh.CompetenciaPonto", "funcionario__empresa_id"),
            "conferencia": ("rh.ConferenciaFolha", "retorno__funcionario__empresa_id"),
        },
        "financeiro": {
            "conta_pagar": ("financeiro.LancamentoFinanceiro", "empresa_id"),
            "conta_receber": ("financeiro.LancamentoFinanceiro", "empresa_id"),
            "parcela": ("financeiro.ParcelaFinanceira", "lancamento__empresa_id"),
            "conta_bancaria": ("financeiro.ContaBancaria", "empresa_id"),
            "importacao_ofx": ("financeiro.ImportacaoOFX", "conta_bancaria__empresa_id"),
            "movimento_ofx": ("financeiro.MovimentoOFX", "conta_bancaria__empresa_id"),
            "transferencia": ("financeiro.TransferenciaBancaria", "conta_origem__empresa_id"),
            "centro_custo": ("financeiro.CentroCusto", "empresa_id"),
        },
    }
    ROTAS_EXATAS = {
        ("compras", "documento_divergencia_resolver"): ("compras.DivergenciaDocumentoCompra", "documento__empresa_id"),
        ("compras", "divergencia_resolver"): ("compras.DivergenciaRecebimento", "recebimento_item__recebimento__pedido__empresa_id"),
        ("compras", "recebimento_detalhe"): ("compras.RecebimentoCompra", "pedido__empresa_id"),
        ("compras", "recebimento_editar"): ("compras.RecebimentoCompra", "pedido__empresa_id"),
        ("compras", "recebimento_confirmar"): ("compras.RecebimentoCompra", "pedido__empresa_id"),
        ("compras", "recebimento_cancelar"): ("compras.RecebimentoCompra", "pedido__empresa_id"),
    }

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.user.is_superuser:
            return None
        match = request.resolver_match
        namespace = match.app_name if match else ""
        nome = match.url_name if match else ""
        pk = view_kwargs.get("pk")
        if not pk:
            return None
        exata = self.ROTAS_EXATAS.get((namespace, nome))
        if exata:
            modelo_nome, empresa_lookup = exata
            modelo = apps.get_model(modelo_nome)
            empresa_id = modelo.objects.filter(pk=pk).values_list(empresa_lookup, flat=True).first()
            if empresa_id is not None and not pode_acessar_empresa(request.user, empresa_id):
                raise PermissionDenied("Registro de empresa não autorizada.")
            return None
        for chave, (modelo_nome, empresa_lookup) in self.ROTAS.get(namespace, {}).items():
            if chave not in nome:
                continue
            modelo = apps.get_model(modelo_nome)
            empresa_id = modelo.objects.filter(pk=pk).values_list(empresa_lookup, flat=True).first()
            if empresa_id is not None and not pode_acessar_empresa(request.user, empresa_id):
                raise PermissionDenied("Registro de empresa não autorizada.")
            break
        return None

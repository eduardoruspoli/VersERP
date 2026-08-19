from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone

from comercial.models import Proposta
from compras.models import DivergenciaDocumentoCompra, DocumentoCompra, PedidoCompra
from financeiro.models import ContaBancaria, LancamentoFinanceiro, MovimentacaoBancaria, ParcelaFinanceira
from rh.models import CompetenciaPonto, ConferenciaFolha

from .access import ids_empresas_usuario

ZERO = Decimal("0.00")


def _saldo_parcelas(empresas, tipo, hoje):
    parcelas = ParcelaFinanceira.objects.filter(lancamento__empresa__in=empresas,lancamento__tipo=tipo).exclude(status="CANCELADA").exclude(lancamento__status="CANCELADO").prefetch_related("baixas")
    aberto=vencido=ZERO
    for parcela in parcelas:
        saldo=max(parcela.valor-sum((b.valor for b in parcela.baixas.all()),ZERO),ZERO)
        aberto+=saldo
        if parcela.vencimento < hoje: vencido+=saldo
    return aberto,vencido


def indicadores_dashboard(usuario):
    empresas=ids_empresas_usuario(usuario); hoje=timezone.localdate(); limite=hoje+timedelta(days=7)
    receber,receber_vencido=_saldo_parcelas(empresas,"RECEBER",hoje)
    pagar,pagar_vencido=_saldo_parcelas(empresas,"PAGAR",hoje)
    contas=ContaBancaria.objects.filter(empresa__in=empresas,ativa=True)
    saldo_inicial=contas.aggregate(total=Sum("saldo_inicial"))["total"] or ZERO
    movimentos=MovimentacaoBancaria.objects.filter(conta_bancaria__in=contas).values("tipo").annotate(total=Sum("valor"))
    mapa={i["tipo"]:i["total"] for i in movimentos}; saldo=saldo_inicial+mapa.get("ENTRADA",ZERO)-mapa.get("SAIDA",ZERO)
    propostas=Proposta.objects.filter(empresa__in=empresas,status__in=[Proposta.Status.RASCUNHO,Proposta.Status.EM_REVISAO,Proposta.Status.ENVIADA,Proposta.Status.EM_NEGOCIACAO])
    alertas={
        "receber_vencido":receber_vencido,"pagar_vencido":pagar_vencido,
        "propostas_vencendo":propostas.filter(revisoes__numero=F("revisao_atual"),revisoes__valida_ate__range=(hoje,limite)).count(),
        "pedidos_aprovacao":PedidoCompra.objects.filter(empresa__in=empresas,status=PedidoCompra.Status.AGUARDANDO_APROVACAO).count(),
        "pedidos_pendentes":PedidoCompra.objects.filter(empresa__in=empresas,status__in=[PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO]).count(),
        "documentos_divergentes":DocumentoCompra.objects.filter(empresa__in=empresas,status=DocumentoCompra.Status.DIVERGENTE).count(),
        "documentos_integracao":DocumentoCompra.objects.filter(empresa__in=empresas,status=DocumentoCompra.Status.CONFERIDO,integracao_financeira__isnull=True).count(),
        "rh_pendente":CompetenciaPonto.objects.filter(funcionario__empresa__in=empresas).exclude(status=CompetenciaPonto.Status.FECHADO).count(),
        "bh_negativo":CompetenciaPonto.objects.filter(funcionario__empresa__in=empresas,saldo_final_minutos__lt=0).count(),
        "folha_divergente":ConferenciaFolha.objects.filter(retorno__funcionario__empresa__in=empresas,status=ConferenciaFolha.Status.DIVERGENTE).count(),
    }
    return {"receber":receber,"pagar":pagar,"saldo":saldo,"propostas_abertas":propostas.count(),"alertas":alertas,
            "ultimas_propostas":propostas.select_related("cliente","empresa").order_by("-criado_em")[:5],
            "ultimos_lancamentos":LancamentoFinanceiro.objects.filter(empresa__in=empresas).select_related("empresa","pessoa").order_by("-criado_em")[:5]}
def pendencias_usuario(usuario):
    dados=indicadores_dashboard(usuario)
    alertas = dados["alertas"]
    permitidas = {}
    if usuario.has_perm("financeiro.view_lancamentofinanceiro"):
        for chave in ("receber_vencido", "pagar_vencido"):
            permitidas[chave] = alertas[chave]
    if usuario.has_perm("comercial.view_proposta"):
        permitidas["propostas_vencendo"] = alertas["propostas_vencendo"]
    if usuario.has_perm("compras.view_pedidocompra"):
        for chave in ("pedidos_aprovacao", "pedidos_pendentes", "documentos_divergentes", "documentos_integracao"):
            permitidas[chave] = alertas[chave]
    if usuario.has_perm("rh.view_rh"):
        for chave in ("rh_pendente", "bh_negativo", "folha_divergente"):
            permitidas[chave] = alertas[chave]
    return permitidas

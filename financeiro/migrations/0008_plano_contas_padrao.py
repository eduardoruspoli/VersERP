from django.db import migrations, models


CONTAS = [
    ("1", "Ativo", None, False),
    ("1.01", "Ativo Circulante", "1", False),
    ("1.01.01", "Disponibilidades", "1.01", False),
    ("1.01.01.001", "Caixa", "1.01.01", True),
    ("1.01.01.002", "Bancos Conta Movimento", "1.01.01", True),
    ("1.01.01.003", "Aplicações Financeiras de Liquidez Imediata", "1.01.01", True),
    ("1.01.02", "Clientes e Contas a Receber", "1.01", False),
    ("1.01.02.001", "Clientes Nacionais", "1.01.02", True),
    ("1.01.02.002", "Outros Valores a Receber", "1.01.02", True),
    ("1.01.03", "Adiantamentos", "1.01", False),
    ("1.01.03.001", "Adiantamentos a Fornecedores", "1.01.03", True),
    ("1.01.03.002", "Adiantamentos a Empregados", "1.01.03", True),
    ("1.01.04", "Estoques", "1.01", False),
    ("1.01.04.001", "Mercadorias para Revenda", "1.01.04", True),
    ("1.01.04.002", "Materiais e Insumos", "1.01.04", True),
    ("1.01.05", "Tributos a Recuperar", "1.01", False),
    ("1.01.05.001", "ICMS a Recuperar", "1.01.05", True),
    ("1.01.05.002", "PIS e COFINS a Recuperar", "1.01.05", True),
    ("1.01.05.003", "Outros Tributos a Recuperar", "1.01.05", True),
    ("1.02", "Ativo Não Circulante", "1", False),
    ("1.02.01", "Realizável a Longo Prazo", "1.02", False),
    ("1.02.01.001", "Créditos a Longo Prazo", "1.02.01", True),
    ("1.02.02", "Imobilizado", "1.02", False),
    ("1.02.02.001", "Máquinas e Equipamentos", "1.02.02", True),
    ("1.02.02.002", "Móveis e Utensílios", "1.02.02", True),
    ("1.02.02.003", "Veículos", "1.02.02", True),
    ("1.02.02.004", "Equipamentos de Informática", "1.02.02", True),
    ("1.02.02.900", "Depreciação Acumulada", "1.02.02", True),
    ("2", "Passivo", None, False),
    ("2.01", "Passivo Circulante", "2", False),
    ("2.01.01", "Fornecedores", "2.01", False),
    ("2.01.01.001", "Fornecedores Nacionais", "2.01.01", True),
    ("2.01.02", "Obrigações Trabalhistas", "2.01", False),
    ("2.01.02.001", "Salários a Pagar", "2.01.02", True),
    ("2.01.02.002", "Encargos Sociais a Recolher", "2.01.02", True),
    ("2.01.02.003", "Férias e Décimo Terceiro a Pagar", "2.01.02", True),
    ("2.01.03", "Obrigações Tributárias", "2.01", False),
    ("2.01.03.001", "Tributos Federais a Recolher", "2.01.03", True),
    ("2.01.03.002", "Tributos Estaduais a Recolher", "2.01.03", True),
    ("2.01.03.003", "Tributos Municipais a Recolher", "2.01.03", True),
    ("2.01.04", "Empréstimos e Financiamentos", "2.01", False),
    ("2.01.04.001", "Empréstimos Bancários de Curto Prazo", "2.01.04", True),
    ("2.01.04.002", "Financiamentos de Curto Prazo", "2.01.04", True),
    ("2.01.05", "Outras Obrigações", "2.01", False),
    ("2.01.05.001", "Aluguéis a Pagar", "2.01.05", True),
    ("2.01.05.002", "Contas e Serviços a Pagar", "2.01.05", True),
    ("2.01.05.003", "Outros Valores a Pagar", "2.01.05", True),
    ("2.02", "Passivo Não Circulante", "2", False),
    ("2.02.01", "Empréstimos e Financiamentos de Longo Prazo", "2.02", False),
    ("2.02.01.001", "Empréstimos Bancários de Longo Prazo", "2.02.01", True),
    ("2.02.01.002", "Financiamentos de Longo Prazo", "2.02.01", True),
    ("2.02.02", "Outras Obrigações de Longo Prazo", "2.02", False),
    ("2.02.02.001", "Outros Valores a Pagar a Longo Prazo", "2.02.02", True),
    ("3", "Patrimônio Líquido", None, False),
    ("3.01", "Capital Social", "3", False),
    ("3.01.01", "Capital Social Integralizado", "3.01", True),
    ("3.02", "Reservas", "3", False),
    ("3.02.01", "Reserva Legal", "3.02", True),
    ("3.02.02", "Outras Reservas", "3.02", True),
    ("3.03", "Resultados Acumulados", "3", False),
    ("3.03.01", "Lucros Acumulados", "3.03", True),
    ("3.03.02", "Prejuízos Acumulados", "3.03", True),
    ("4", "Receitas", None, False),
    ("4.01", "Receitas Operacionais", "4", False),
    ("4.01.01", "Receita de Serviços", "4.01", True),
    ("4.01.02", "Receita de Vendas de Mercadorias", "4.01", True),
    ("4.01.03", "Outras Receitas Operacionais", "4.01", True),
    ("4.02", "Receitas Financeiras", "4", False),
    ("4.02.01", "Rendimentos de Aplicações Financeiras", "4.02", True),
    ("4.02.02", "Juros e Descontos Obtidos", "4.02", True),
    ("4.02.03", "Outras Receitas Financeiras", "4.02", True),
    ("5", "Custos", None, False),
    ("5.01", "Custos dos Serviços Prestados", "5", False),
    ("5.01.01", "Materiais Aplicados em Serviços", "5.01", True),
    ("5.01.02", "Mão de Obra Aplicada em Serviços", "5.01", True),
    ("5.01.03", "Serviços de Terceiros Aplicados", "5.01", True),
    ("5.01.04", "Equipamentos e Locações Aplicados", "5.01", True),
    ("5.01.05", "Deslocamentos Diretamente Aplicados", "5.01", True),
    ("5.01.99", "Outros Custos dos Serviços", "5.01", True),
    ("5.02", "Custos das Mercadorias Vendidas", "5", False),
    ("5.02.01", "Custo das Mercadorias Vendidas", "5.02", True),
    ("6", "Despesas", None, False),
    ("6.01", "Despesas Administrativas", "6", False),
    ("6.01.01", "Material de Escritório e Expediente", "6.01", True),
    ("6.01.02", "Cartórios, Taxas e Associações", "6.01", True),
    ("6.01.03", "Viagens e Representações Administrativas", "6.01", True),
    ("6.01.99", "Outras Despesas Administrativas", "6.01", True),
    ("6.02", "Despesas com Pessoal", "6", False),
    ("6.02.01", "Salários e Pró-labore", "6.02", True),
    ("6.02.02", "Encargos Sociais e Trabalhistas", "6.02", True),
    ("6.02.03", "Benefícios", "6.02", True),
    ("6.02.04", "Treinamentos e Capacitação", "6.02", True),
    ("6.03", "Despesas Comerciais", "6", False),
    ("6.03.01", "Publicidade e Marketing", "6.03", True),
    ("6.03.02", "Comissões sobre Vendas", "6.03", True),
    ("6.03.03", "Fretes e Entregas", "6.03", True),
    ("6.03.04", "Viagens e Representações Comerciais", "6.03", True),
    ("6.04", "Despesas de Ocupação e Estrutura", "6", False),
    ("6.04.01", "Aluguéis e Condomínios", "6.04", True),
    ("6.04.02", "Energia Elétrica", "6.04", True),
    ("6.04.03", "Água e Saneamento", "6.04", True),
    ("6.04.04", "Manutenção e Conservação", "6.04", True),
    ("6.04.05", "Segurança e Limpeza", "6.04", True),
    ("6.05", "Despesas com Veículos", "6", False),
    ("6.05.01", "Combustíveis e Lubrificantes", "6.05", True),
    ("6.05.02", "Manutenção de Veículos", "6.05", True),
    ("6.05.03", "Seguros, Licenciamento e Pedágios", "6.05", True),
    ("6.06", "Despesas com Tecnologia", "6", False),
    ("6.06.01", "Softwares e Assinaturas", "6.06", True),
    ("6.06.02", "Internet e Telecomunicações", "6.06", True),
    ("6.06.03", "Equipamentos e Suprimentos de Informática", "6.06", True),
    ("6.07", "Serviços de Terceiros", "6", False),
    ("6.07.01", "Contabilidade", "6.07", True),
    ("6.07.02", "Consultoria e Assessoria", "6.07", True),
    ("6.07.03", "Serviços Jurídicos", "6.07", True),
    ("6.07.04", "Outros Serviços de Terceiros", "6.07", True),
    ("6.08", "Despesas Tributárias", "6", False),
    ("6.08.01", "Impostos, Taxas e Contribuições", "6.08", True),
    ("6.08.02", "Multas Fiscais e Administrativas", "6.08", True),
    ("6.09", "Despesas Financeiras", "6", False),
    ("6.09.01", "Tarifas Bancárias", "6.09", True),
    ("6.09.02", "Juros e Encargos Financeiros", "6.09", True),
    ("6.09.03", "Descontos Concedidos", "6.09", True),
    ("6.10", "Outras Despesas Operacionais", "6", False),
    ("6.10.01", "Seguros Gerais", "6.10", True),
    ("6.10.02", "Perdas e Indenizações", "6.10", True),
    ("6.10.99", "Outras Despesas Operacionais", "6.10", True),
]


TIPOS = {
    "1": ("ATIVO", "DEVEDORA"),
    "2": ("PASSIVO", "CREDORA"),
    "3": ("PATRIMONIO_LIQUIDO", "CREDORA"),
    "4": ("RECEITA", "CREDORA"),
    "5": ("CUSTO", "DEVEDORA"),
    "6": ("DESPESA", "DEVEDORA"),
}


CONTAS_REDUTORAS = {
    "1.02.02.900": "CREDORA",
    "3.03.02": "DEVEDORA",
}


def criar_plano_padrao(apps, schema_editor):
    PlanoConta = apps.get_model("financeiro", "PlanoConta")
    contas_por_codigo = {
        conta.codigo: conta
        for conta in PlanoConta.objects.all()
    }

    for codigo, nome, codigo_pai, aceita_lancamento in CONTAS:
        tipo, natureza_padrao = TIPOS[codigo.split(".")[0]]
        natureza = CONTAS_REDUTORAS.get(codigo, natureza_padrao)
        conta_pai = contas_por_codigo.get(codigo_pai)

        conta, _ = PlanoConta.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nome": nome,
                "tipo": tipo,
                "natureza": natureza,
                "conta_redutora": codigo in CONTAS_REDUTORAS,
                "conta_pai": conta_pai,
                "aceita_lancamento": aceita_lancamento,
                "estrutural": not aceita_lancamento,
                "ativo": True,
            },
        )
        contas_por_codigo[codigo] = conta


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0007_plano_contabil"),
    ]

    operations = [
        migrations.AddField(
            model_name="planoconta",
            name="conta_redutora",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Permite natureza inversa à padrão do grupo "
                    "para contas contábeis redutoras."
                ),
                verbose_name="Conta redutora",
            ),
        ),
        migrations.RunPython(
            criar_plano_padrao,
            migrations.RunPython.noop,
        ),
    ]

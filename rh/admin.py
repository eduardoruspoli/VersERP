from django.contrib import admin

from .models import (ApuracaoDiaria, CompetenciaPonto, ConferenciaFolha,
                     ContratoFuncionario, EventoFolha, Feriado, Funcionario,
                     HistoricoRH, Jornada, JornadaDia, MarcacaoPonto,
                     OcorrenciaPonto, RetornoContabilidade, ValeAdiantamento,
                     ValeParcela)

admin.site.register([Funcionario, ContratoFuncionario, Jornada, JornadaDia, Feriado,
                     CompetenciaPonto, MarcacaoPonto, OcorrenciaPonto, ApuracaoDiaria,
                     EventoFolha, ValeAdiantamento, ValeParcela, RetornoContabilidade,
                     ConferenciaFolha, HistoricoRH])

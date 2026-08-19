# Importação histórica

Primeiro execute:

```powershell
python manage.py importar_propostas_historicas arquivo.xlsx --empresa ID --dry-run
```

CSV aceita cabeçalhos `numero`, `data`, `cliente`, `servico`, `valor`, `status`, `contato` e `observacao`. XLSX requer `requirements-importacao.txt`. O comando normaliza nomes, reutiliza correspondências exatas, sinaliza ambiguidade, não inventa campos, preserva status histórico e não duplica números já existentes. Revise o relatório antes da execução sem `--dry-run` e mantenha backup.

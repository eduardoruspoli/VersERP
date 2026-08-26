# Importação histórica

O importador confirmado é o comando de propostas históricas:

```powershell
python manage.py importar_propostas_historicas arquivo.xlsx --empresa ID --dry-run
```

Execute primeiro com `--dry-run`, revise contagens, erros, duplicidades, clientes incompletos e revisões sem proposta-base. Somente depois, com backup e empresa correta, avalie a execução real.

O comando trata CSV com cabeçalhos suportados e XLSX no formato reconhecido pelo importador. XLSX requer instalação separada de `requirements-importacao.txt`. A rotina normaliza dados, reutiliza correspondências exatas, sinaliza ambiguidades, preserva status/revisões históricas e evita números já existentes.

Existe também o comando de enriquecimento de propostas históricas, destinado a completar dados conforme suas opções próprias. Consulte `python manage.py enriquecer_propostas_historicas --help` antes de qualquer uso.

Não execute importadores sobre dados reais sem dry-run, backup, recorte de empresa e revisão do relatório.

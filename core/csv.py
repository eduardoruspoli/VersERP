def celula_csv_segura(valor):
    """Impede que planilhas interpretem conteúdo exportado como fórmula."""
    texto = "" if valor is None else str(valor)
    if texto.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


def linha_csv_segura(valores):
    return [celula_csv_segura(valor) for valor in valores]

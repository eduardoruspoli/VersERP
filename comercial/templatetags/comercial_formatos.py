from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def moeda_br(valor):
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return "0,00"
    return f"{numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

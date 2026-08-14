import hashlib
import re

from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
)


class ErroOFX(ValueError):
    """
    Erro de leitura ou validação
    de um arquivo OFX.
    """


def _decodificar_ofx(conteudo):
    if not conteudo:
        raise ErroOFX(
            "O arquivo OFX está vazio."
        )

    cabecalho = conteudo[
        :4096
    ].decode(
        "latin-1",
        errors="ignore",
    )

    correspondencia = re.search(
        r"CHARSET\s*:\s*([^\r\n]+)",
        cabecalho,
        flags=re.IGNORECASE,
    )

    charset = ""

    if correspondencia:
        charset = (
            correspondencia
            .group(1)
            .strip()
            .upper()
        )

    mapa = {
        "UTF-8": "utf-8",
        "UTF8": "utf-8",
        "1252": "cp1252",
        "WINDOWS-1252": "cp1252",
        "CP1252": "cp1252",
        "ISO-8859-1": "latin-1",
        "8859-1": "latin-1",
        "LATIN1": "latin-1",
        "USASCII": "cp1252",
        "ASCII": "cp1252",
        "NONE": "cp1252",
    }

    codificacao = mapa.get(
        charset,
        "utf-8",
    )

    try:
        return conteudo.decode(
            codificacao
        )

    except UnicodeDecodeError:
        try:
            return conteudo.decode(
                "cp1252"
            )

        except UnicodeDecodeError:
            return conteudo.decode(
                "latin-1",
                errors="replace",
            )


def _normalizar_tags(texto):
    """
    Remove prefixos de namespace do XML.

    Exemplo:
    <ofx:STMTTRN>
    vira
    <STMTTRN>
    """

    return re.sub(
        (
            r"<(/?)"
            r"[A-Za-z_][\w.-]*:"
            r"([A-Za-z0-9_]+)"
        ),
        r"<\1\2",
        texto,
    )


def _valor_tag(
    bloco,
    tag,
):
    padrao = (
        rf"<{re.escape(tag)}"
        rf"\b[^>]*>\s*"
        rf"([^<\r\n]+)"
    )

    correspondencia = re.search(
        padrao,
        bloco,
        flags=re.IGNORECASE,
    )

    if not correspondencia:
        return ""

    return (
        correspondencia
        .group(1)
        .strip()
    )


def _data_ofx(valor):
    if not valor:
        return None

    digitos = re.match(
        r"\s*(\d{8})",
        valor,
    )

    if not digitos:
        return None

    try:
        return datetime.strptime(
            digitos.group(1),
            "%Y%m%d",
        ).date()

    except ValueError:
        return None


def _decimal_ofx(valor):
    if not valor:
        raise ErroOFX(
            "Movimento OFX sem valor."
        )

    texto = (
        valor
        .strip()
        .replace(" ", "")
    )

    if (
        "," in texto
        and "." not in texto
    ):
        texto = texto.replace(
            ",",
            ".",
        )

    try:
        return Decimal(
            texto
        )

    except InvalidOperation as exc:
        raise ErroOFX(
            (
                "Não foi possível interpretar "
                f"o valor OFX: {valor}"
            )
        ) from exc


def _limpar_texto(valor):
    if not valor:
        return ""

    return re.sub(
        r"\s+",
        " ",
        valor,
    ).strip()


def _gerar_identificador(
    indice,
    data,
    valor,
    nome,
    memo,
    referencia,
):
    origem = "|".join(
        [
            str(indice),
            str(data or ""),
            str(valor),
            nome or "",
            memo or "",
            referencia or "",
        ]
    )

    digest = hashlib.sha256(
        origem.encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        "VERSERP-"
        + digest[:40]
    )


def _extrair_blocos_transacoes(
    texto,
):
    padrao = re.compile(
        (
            r"<STMTTRN\b[^>]*>"
            r"(.*?)"
            r"(?:"
            r"</STMTTRN>"
            r"|(?=<STMTTRN\b)"
            r"|(?=</BANKTRANLIST>)"
            r")"
        ),
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    return padrao.findall(
        texto
    )


def _descricao_transacao(
    nome,
    memo,
):
    nome = _limpar_texto(
        nome
    )

    memo = _limpar_texto(
        memo
    )

    if (
        nome
        and memo
        and nome.lower()
        != memo.lower()
    ):
        return (
            f"{nome} - {memo}"
        )[:500]

    return (
        nome
        or memo
        or "Movimento bancário"
    )[:500]


def ler_ofx(arquivo):
    """
    Lê um arquivo OFX e retorna dados
    normalizados para gravação no VersERP.

    Não utiliza serviços externos.

    Retorno:

    {
        "banco_id": "...",
        "agencia": "...",
        "conta": "...",
        "tipo_conta": "...",
        "data_inicio": date | None,
        "data_fim": date | None,
        "movimentos": [
            {
                "identificador": "...",
                "data": date,
                "tipo": "ENTRADA" | "SAIDA",
                "valor": Decimal,
                "descricao": "...",
                "documento": "...",
                "tipo_ofx": "...",
            }
        ],
    }
    """

    try:
        arquivo.seek(0)
    except (
        AttributeError,
        OSError,
    ):
        pass

    conteudo = arquivo.read()

    try:
        arquivo.seek(0)
    except (
        AttributeError,
        OSError,
    ):
        pass

    if isinstance(
        conteudo,
        str,
    ):
        texto = conteudo
    else:
        texto = _decodificar_ofx(
            conteudo
        )

    texto = _normalizar_tags(
        texto
    )

    if not re.search(
        r"<OFX\b",
        texto,
        flags=re.IGNORECASE,
    ):
        raise ErroOFX(
            (
                "O arquivo selecionado não "
                "parece ser um OFX válido."
            )
        )

    banco_id = _valor_tag(
        texto,
        "BANKID",
    )

    agencia = _valor_tag(
        texto,
        "BRANCHID",
    )

    conta = _valor_tag(
        texto,
        "ACCTID",
    )

    tipo_conta = _valor_tag(
        texto,
        "ACCTTYPE",
    )

    data_inicio = _data_ofx(
        _valor_tag(
            texto,
            "DTSTART",
        )
    )

    data_fim = _data_ofx(
        _valor_tag(
            texto,
            "DTEND",
        )
    )

    blocos = (
        _extrair_blocos_transacoes(
            texto
        )
    )

    if not blocos:
        raise ErroOFX(
            (
                "Nenhuma movimentação bancária "
                "foi encontrada no arquivo OFX."
            )
        )

    movimentos = []

    for indice, bloco in enumerate(
        blocos,
        start=1,
    ):
        data = _data_ofx(
            _valor_tag(
                bloco,
                "DTPOSTED",
            )
        )

        if data is None:
            data = _data_ofx(
                _valor_tag(
                    bloco,
                    "DTUSER",
                )
            )

        if data is None:
            raise ErroOFX(
                (
                    "Foi encontrada uma transação "
                    "sem data válida no arquivo."
                )
            )

        valor_assinado = (
            _decimal_ofx(
                _valor_tag(
                    bloco,
                    "TRNAMT",
                )
            )
        )

        if (
            valor_assinado
            == Decimal("0")
        ):
            continue

        if (
            valor_assinado
            < Decimal("0")
        ):
            tipo = "SAIDA"
        else:
            tipo = "ENTRADA"

        valor = abs(
            valor_assinado
        )

        fitid = _limpar_texto(
            _valor_tag(
                bloco,
                "FITID",
            )
        )

        nome = _valor_tag(
            bloco,
            "NAME",
        )

        memo = _valor_tag(
            bloco,
            "MEMO",
        )

        referencia = (
            _valor_tag(
                bloco,
                "REFNUM",
            )
            or _valor_tag(
                bloco,
                "CHECKNUM",
            )
        )

        if not fitid:
            fitid = (
                _gerar_identificador(
                    indice=indice,
                    data=data,
                    valor=valor_assinado,
                    nome=nome,
                    memo=memo,
                    referencia=referencia,
                )
            )

        movimentos.append(
            {
                "identificador": (
                    fitid[:255]
                ),

                "data": data,

                "tipo": tipo,

                "valor": valor,

                "descricao": (
                    _descricao_transacao(
                        nome,
                        memo,
                    )
                ),

                "documento": (
                    _limpar_texto(
                        referencia
                    )[:100]
                ),

                "tipo_ofx": (
                    _limpar_texto(
                        _valor_tag(
                            bloco,
                            "TRNTYPE",
                        )
                    )
                ),
            }
        )

    if not movimentos:
        raise ErroOFX(
            (
                "O arquivo OFX não possui "
                "movimentações com valor diferente de zero."
            )
        )

    datas = [
        movimento["data"]
        for movimento
        in movimentos
    ]

    if data_inicio is None:
        data_inicio = min(
            datas
        )

    if data_fim is None:
        data_fim = max(
            datas
        )

    return {
        "banco_id": banco_id,
        "agencia": agencia,
        "conta": conta,
        "tipo_conta": tipo_conta,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "movimentos": movimentos,
    }
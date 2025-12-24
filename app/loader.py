import csv
import os
from typing import Dict, List, Optional


# =================================================
# Caminho base dos CSV
# =================================================

BASE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "anexos"
)


# =================================================
# Utilitário genérico para carregar CSV
# =================================================

def load_csv(filename: str) -> List[Dict]:
    path = os.path.join(BASE_PATH, filename)
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


# =================================================
# Helper para fundamento estruturado
# =================================================

def fundamento(regra: str, motivo: str) -> Dict[str, str]:
    return {
        "regra": regra,
        "motivo": motivo
    }


# =================================================
# Carga inicial (em memória)
# =================================================

CCLASTRIB_TABLE = load_csv("cclastrib.csv")
IBS_TABLE = load_csv("ibs_aliquotas.csv")
CBS_TABLE = load_csv("cbs_aliquotas.csv")
TRANS_IBS = load_csv("transicao_ibs.csv")
TRANS_CBS = load_csv("transicao_cbs.csv")
NCM_EXCECOES = load_csv("ncm_excecoes.csv")


# =================================================
# Funções auxiliares de matching
# =================================================

def match(valor: str, regra: str) -> bool:
    """
    *  = qualquer valor
    !  = diferente
    """
    if regra == "*":
        return True
    if regra == "!":
        return False
    return valor == regra


# =================================================
# Resolver CCLASTRIB
# =================================================

def resolver_cclastrib(payload: dict) -> Optional[Dict]:
    emit = payload["emitente"]
    dest = payload["destinatario"]

    for row in CCLASTRIB_TABLE:
        if (
            match(payload["tipo_operacao"], row["tipo_operacao"])
            and match(payload.get("cfop", ""), row["cfop"])
            and match(emit["uf"], row["uf_origem"])
            and (
                row["uf_destino"] == "*"
                or (row["uf_destino"] == "!" and emit["uf"] != dest["uf"])
                or emit["uf"] == dest["uf"]
            )
            and match(emit["regime_fiscal"], row["regime_emitente"])
            and match(
                "S" if dest["consumidor_final"] else "N",
                row["consumidor_final"]
            )
            and match(
                "S" if dest["contribuinte"] else "N",
                row["contribuinte"]
            )
        ):
            return row

    return None


# =================================================
# Buscar alíquota base por CCLASTRIB e ano
# =================================================

def buscar_aliquota(
    table: List[Dict],
    cclastrib: str,
    ano: int
) -> Optional[Dict]:
    for row in table:
        if row["cclastrib"] == cclastrib and int(row["ano"]) == ano:
            return row
    return None


# =================================================
# Aplicar regra de transição
# =================================================

def aplicar_transicao(
    base: float,
    trans_table: List[Dict],
    ano: int
) -> float:
    for row in trans_table:
        if int(row["ano"]) == ano:
            reducao = float(row["percentual_reducao"])
            acrescimo = float(row["percentual_acrescimo"])
            return base * (1 - reducao) * (1 + acrescimo)
    return base


# =================================================
# Aplicar exceção por NCM (se existir)
# =================================================

def aplicar_excecao_ncm(
    ncm: str,
    ano: int
) -> Optional[Dict]:
    for row in NCM_EXCECOES:
        if row["ncm"] == ncm and int(row["ano"]) == ano:
            return row
    return None


# =================================================
# Função principal de cálculo fiscal
# =================================================

def calcular_tributos(payload: dict) -> Dict:
    """
    Calcula IBS, CBS e retorna CCLASTRIB
    de forma determinística, baseada em CSV.
    """

    ano = int(payload["data_emissao"][:4])
    ncm = payload["ncm"]

    # ---------------------------------------------
    # 1) Resolver CCLASTRIB
    # ---------------------------------------------
    cclas = resolver_cclastrib(payload)
    if not cclas:
        return {"pendencia": "CCLASTRIB não identificado para a operação"}

    codigo = cclas["codigo"]

    # ---------------------------------------------
    # 2) Buscar alíquotas base
    # ---------------------------------------------
    ibs_base = buscar_aliquota(IBS_TABLE, codigo, ano)
    cbs_base = buscar_aliquota(CBS_TABLE, codigo, ano)

    if not ibs_base or not cbs_base:
        return {"pendencia": "Alíquotas não encontradas para o ano informado"}

    ibs = float(ibs_base["aliquota"])
    cbs = float(cbs_base["aliquota"])

    # ---------------------------------------------
    # 3) Aplicar transição
    # ---------------------------------------------
    ibs = aplicar_transicao(ibs, TRANS_IBS, ano)
    cbs = aplicar_transicao(cbs, TRANS_CBS, ano)

    # ---------------------------------------------
    # 4) Exceção por NCM
    # ---------------------------------------------
    excecao = aplicar_excecao_ncm(ncm, ano)
    if excecao:
        if excecao.get("aliquota_override"):
            ibs = float(excecao["aliquota_override"])
            cbs = float(excecao["aliquota_override"])
            ibs_base["fundamento_legal"] = excecao["fundamento_legal"]
            cbs_base["fundamento_legal"] = excecao["fundamento_legal"]

        if excecao.get("cclastrib_override"):
            codigo = excecao["cclastrib_override"]

    # ---------------------------------------------
    # 5) Retorno estruturado (compatível com schema)
    # ---------------------------------------------
    return {
        "cclastrib": {
            "codigo": codigo,
            "descricao": cclas["descricao"],
            "fundamento": [
                fundamento(
                    cclas["fundamento_legal"],
                    "Classificação da operação conforme dados fiscais informados"
                )
            ]
        },
        "ibs": {
            "aliquota": round(ibs, 4),
            "fundamento": [
                fundamento(
                    ibs_base["fundamento_legal"],
                    "Alíquota do IBS definida conforme legislação e anexo aplicável"
                )
            ]
        },
        "cbs": {
            "aliquota": round(cbs, 4),
            "fundamento": [
                fundamento(
                    cbs_base["fundamento_legal"],
                    "Alíquota da CBS definida conforme legislação e anexo aplicável"
                )
            ]
        }
    }

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, List, Optional, Tuple


# -------------------------
# Utilitários de normalização
# -------------------------
def norm_ncm(ncm: str) -> str:
    # remove tudo que não for dígito (tira pontos)
    digits = re.sub(r"\D+", "", (ncm or ""))
    return digits


def norm_code(code: str) -> str:
    return (code or "").strip().upper()


def parse_float_ptbr(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # aceita "4,50%" ou "0,12" etc
    s = s.replace("%", "").strip()
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except Exception:
        return None


def today_if_none(d: Optional[date]) -> date:
    return d if d else date.today()


# -------------------------
# Leitura CSV (separador ;)
# -------------------------
def read_csv_semicolon(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = []
        for r in reader:
            rows.append({
                k.strip().replace("\ufeff", ""): (v.strip() if isinstance(v, str) else v)
                for k, v in r.items()
            })
        return rows


# -------------------------
# Data sources (carregados do /data/anexos)
# -------------------------
@dataclass
class DataSources:
    base_dir: str
    ncm_master: List[Dict[str, str]]
    ncm_excecoes: List[Dict[str, str]]
    ibs_aliquotas: List[Dict[str, str]]
    cbs_aliquotas: List[Dict[str, str]]
    transicao_ibs: List[Dict[str, str]]
    transicao_cbs: List[Dict[str, str]]
    cclastrib: List[Dict[str, str]]
    cst_ibs_cbs_map: List[Dict[str, str]]

    # modelos de anexos (ex: essenciais, alimentos in natura, agro, medicos, etc.)
    anexos_models: Dict[str, List[Dict[str, str]]]


def load_sources(data_anexos_dir: str) -> DataSources:
    def p(name: str) -> str:
        return os.path.join(data_anexos_dir, name)

    anexos_models: Dict[str, List[Dict[str, str]]] = {}
    # tudo que terminar com _model.csv vira "modelo"
    for fname in os.listdir(data_anexos_dir):
        if fname.lower().endswith("_model.csv"):
            anexos_models[fname] = read_csv_semicolon(p(fname))

    return DataSources(
        base_dir=data_anexos_dir,
        ncm_master=read_csv_semicolon(p("ncm_master.csv")),
        ncm_excecoes=read_csv_semicolon(p("ncm_excecoes.csv")),
        ibs_aliquotas=read_csv_semicolon(p("ibs_aliquotas.csv")),
        cbs_aliquotas=read_csv_semicolon(p("cbs_aliquotas.csv")),
        transicao_ibs=read_csv_semicolon(p("transicao_ibs.csv")),
        transicao_cbs=read_csv_semicolon(p("transicao_cbs.csv")),
        cclastrib=read_csv_semicolon(p("cclastrib.csv")),
        cst_ibs_cbs_map=read_csv_semicolon(p("cst_ibs_cbs_map.csv")),
        anexos_models=anexos_models,
    )


# -------------------------
# Lookup helpers
# -------------------------

def dentro_da_vigencia(
    data: date,
    inicio: Optional[str],
    fim: Optional[str]
) -> bool:
    if not inicio:
        return True

    d_ini = date.fromisoformat(inicio)
    if data < d_ini:
        return False

    if fim:
        d_fim = date.fromisoformat(fim)
        if data > d_fim:
            return False

    return True

def find_in_master(
    sources: DataSources,
    ncm_digits: str,
    data_emissao: date,
) -> Optional[Dict[str, str]]:

    for r in sources.ncm_master:
        raw = r.get("ncm", "")
        if not raw:
            continue

        if norm_ncm(raw)[:8] != ncm_digits[:8]:
            continue

        vig_ini = r.get("vigencia_inicio")
        vig_fim = r.get("vigencia_fim")

        if vig_ini:
            if data_emissao < date.fromisoformat(vig_ini):
                continue

        if vig_fim:
            if data_emissao > date.fromisoformat(vig_fim):
                continue

        return r

    return None



def find_excecao(
    sources: DataSources,
    ncm_digits: str,
    data_emissao: date,
) -> Optional[Dict[str, str]]:

    for r in sources.ncm_excecoes:
        raw = r.get("ncm", "")
        if not raw:
            continue

        if norm_ncm(raw)[:8] != ncm_digits[:8]:
            continue

        if not dentro_da_vigencia(
            data_emissao,
            r.get("vigencia_inicio"),
            r.get("vigencia_fim"),
        ):
            continue

        return r

    return None


def year_factor_transicao(
    rows: List[Dict[str, str]],
    year: int,
    campo_percentual: str
) -> Optional[float]:
    """
    Ex:
      campo_percentual = 'percentual_ibs'
      campo_percentual = 'percentual_cbs'
    """
    for r in rows:
        ano = str(r.get("ano", "")).strip()
        if ano == str(year):
            raw = r.get(campo_percentual)
            if raw is None or raw == "":
                return None

            v = parse_float_ptbr(raw)
            return v  # JÁ está em formato decimal (0.001, 0.009)

    return None


def base_aliquota(rows: List[Dict[str, str]], keyname: str) -> Optional[float]:
    """
    ibs_aliquotas.csv / cbs_aliquotas.csv:
      tipo;aliquota
    Ex: tipo=PADRAO aliquota=0.17
    """
    keyname = norm_code(keyname)
    for r in rows:
        t = norm_code(r.get("tipo") or r.get("TIPO") or "")
        if t == keyname:
            v = parse_float_ptbr(r.get("aliquota") or r.get("ALIQUOTA"))
            if v is None:
                return None
            return v / 100.0 if v > 1 else v
    return None

def map_cst_ibs_cbs_from_cclastrib(
    sources: DataSources,
    cclastrib_codigo: str
) -> Tuple[str, str, str]:

    for r in sources.cst_ibs_cbs_map:
        if r.get("cclastrib_codigo") == cclastrib_codigo:
            return (
                r.get("cst_ibs_cbs"),
                r.get("cclass_trib"),
                r.get("descricao"),
            )

    # fallback seguro
    return ("000", "000001", "Tributação integral - padrão")

def pick_cclastrib(sources: DataSources, regime: str, cfop: str, uf_e: str, uf_d: str, cst_icms: str) -> Tuple[str, str, List[Dict[str, str]]]:
    """
    cclastrib.csv deve ser sua tabela de "classificação" operacional.
    Esperamos colunas aproximadas:
      codigo;descricao;regime;cfop;uf_emitente;uf_destinatario;cst_icms;...
    Você pode ir enriquecendo depois.
    """
    regime = norm_code(regime)
    cfop = norm_code(cfop)
    uf_e = norm_code(uf_e)
    uf_d = norm_code(uf_d)
    cst_icms = norm_code(cst_icms)

    candidatos = []
    for r in sources.cclastrib:
        r_reg = norm_code(r.get("regime") or r.get("regime_fiscal") or "")
        r_cfop = norm_code(r.get("cfop") or "")
        r_ufe = norm_code(r.get("uf_emitente") or "")
        r_ufd = norm_code(r.get("uf_destinatario") or "")
        r_cst = norm_code(r.get("cst_icms") or "")

        # match flexível: se a célula vier vazia, vira "coringa"
        ok = True
        if r_reg and r_reg != regime:
            ok = False
        if r_cfop and r_cfop != cfop:
            ok = False
        if r_ufe and r_ufe != uf_e:
            ok = False
        if r_ufd and r_ufd != uf_d:
            ok = False
        if r_cst and r_cst != cst_icms:
            ok = False

        if ok:
            candidatos.append(r)

    # prioriza o mais "específico" (mais campos preenchidos)
    def score(r: Dict[str, str]) -> int:
        keys = ["regime", "regime_fiscal", "cfop", "uf_emitente", "uf_destinatario", "cst_icms"]
        return sum(1 for k in keys if (r.get(k) or "").strip())

    candidatos.sort(key=score, reverse=True)

    if candidatos:
        top = candidatos[0]
        return (
            top.get("codigo") or top.get("CODIGO") or "REGRA-GERAL",
            top.get("descricao") or top.get("DESCRICAO") or "Regra geral",
            candidatos,
        )

    return ("REGRA-GERAL", "Regra geral (sem match em cclastrib.csv)", [])


def map_cst_ibs_cbs_from_categoria(categoria: str) -> Tuple[str, str]:
    """
    Você pediu: "o json deve retornar o cst IBS/CBS".
    Aqui a gente define um default por categoria.
    Depois você pode migrar isso pra CSV (ex: tabela de mapeamento).
    """
    cat = norm_code(categoria)
    # defaults conservadores
    if cat in ("ESSENCIAL", "ALIMENTOS_IN_NATURA", "ALIMENTOS_PROCESSADOS"):
        return ("cst000", "000001")
    if cat in ("AGRO_INSUMOS", "EQUIPAMENTOS_MEDICOS"):
        return ("cst000", "000001")
    # regra geral
    return ("cst000", "000001")


def apply_reducao(aliquota: float, p_redutor: Optional[float]) -> float:
    if aliquota is None:
        return aliquota
    if p_redutor is None:
        return aliquota
    # pRedutor = 5 significa 5% de redução (multiplicador 0.95)
    return aliquota * (1.0 - (p_redutor / 100.0))


# -------------------------
# Motor principal: calcula IBS/CBS e tags XML
# -------------------------


def should_apply_is(data_emissao: date, categoria: Optional[str]) -> bool:
    # você pediu: IS só pra 2027+ e itens nocivos
    if data_emissao.year < 2027:
        return False
    cat = norm_code(categoria or "")
    return cat in ("NOCIVO", "SELETIVO", "BEBIDAS", "CIGARROS")  # ajuste conforme seu ncm_master

def compute_ibs_cbs(
    sources: DataSources,
    *,
    ncm: str,
    data_emissao: date,
    categoria_hint: Optional[str],
) -> Dict[str, Any]:

    fundamentos: List[Dict[str, str]] = []
    year = data_emissao.year

    ibs = year_factor_transicao(
        sources.transicao_ibs,
        year,
        "percentual_ibs"
    ) or 0.0

    cbs = year_factor_transicao(
        sources.transicao_cbs,
        year,
        "percentual_cbs"
    ) or 0.0

    fundamentos.append({
        "regra": "ANO DE REFERÊNCIA",
        "motivo": f"Cálculo realizado com base no ano {year}",
        "fonte": "data_emissao"
    })

    fundamentos.append({
        "regra": "TRANSIÇÃO IBS",
        "motivo": f"Percentual IBS aplicado para {year}: {ibs}",
        "fonte": "transicao_ibs.csv"
    })

    fundamentos.append({
        "regra": "TRANSIÇÃO CBS",
        "motivo": f"Percentual CBS aplicado para {year}: {cbs}",
        "fonte": "transicao_cbs.csv"
    })

    return {
        "ano_referencia": year,
        "aliquota_ibs": ibs,
        "aliquota_cbs": cbs,
        "p_red_ibs": None,
        "p_red_cbs": None,
        "fundamentos": fundamentos,
    }


def classify(
    sources: DataSources,
    regime: str,
    cfop: str,
    uf_emit: str,
    uf_dest: str,
    cst_icms: str,
    ncm: str,
    data_emissao: date,
    compra_gov: bool,
    ind_doacao: bool,
) -> Dict[str, Any]:

    fundamentos_gerais: List[Dict[str, str]] = []
    alertas: List[str] = []
    pendencias: List[str] = []

    # -------------------------
    # NCM / Categoria
    # -------------------------
    ncm_digits = norm_ncm(ncm)

# 🔎 DEBUG TEMPORÁRIO — COLOQUE AQUI
    print("DEBUG NCM solicitado:", ncm_digits)
    print("DEBUG total de NCMs no master:", len(sources.ncm_master))

    found = False
    for r in sources.ncm_master:
        raw = r.get("ncm") or r.get("NCM") or ""
        if norm_ncm(raw)[:8] == ncm_digits[:8]:
            print("MATCH NCM MASTER:", r)
            found = True

    if not found:
        print("⚠️ NENHUM MATCH ENCONTRADO NO NCM_MASTER")

    #row = find_excecao(sources, ncm_digits) or find_in_master(sources, ncm_digits)
    row = (
    find_excecao(sources, ncm_digits, data_emissao)
    or find_in_master(sources, ncm_digits, data_emissao)
)

    categoria = None
    if row:
        categoria_raw = (row.get("categoria") or row.get("CATEGORIA") or "").strip()
        categoria = categoria_raw or None

        if categoria:
            fundamentos_gerais.append({
                "regra": "CATEGORIA NCM",
                "motivo": f"Categoria={categoria}",
                "fonte": "ncm_master.csv / ncm_excecoes.csv"
            })
    else:
        pendencias.append(
            f"NCM {ncm_digits} não encontrado em ncm_master/ncm_excecoes"
        )
        alertas.append(
            "Tributação aplicada pela regra geral (fallback)"
        )


    # -------------------------
    # cClasTrib operacional
    # -------------------------
    cod_cclastrib, desc_cclastrib, _ = pick_cclastrib(
        sources, regime, cfop, uf_emit, uf_dest, cst_icms
    )

    fundamentos_gerais.append({
        "regra": "cClasTrib",
        "motivo": f"Selecionado {cod_cclastrib}",
        "fonte": "cclastrib.csv"
    })

    # -------------------------
    # CST / cClassTrib IBS-CBS (VINDO DO CSV OFICIAL)
    # -------------------------
    cst_ibs_cbs, cclass_trib = map_cst_ibs_cbs_from_categoria(
        categoria or "GERAL"
    )

    fundamentos_gerais.append({
        "regra": "CST IBS/CBS",
        "motivo": f"CST={cst_ibs_cbs} cClassTrib={cclass_trib}",
        "fonte": "cst_ibs_cbs_map.csv"
    })

    # -------------------------
    # Alíquotas IBS / CBS (transição)
    # -------------------------
    calc = compute_ibs_cbs(
        sources,
        ncm=ncm,
        data_emissao=data_emissao,
        categoria_hint=categoria
    )

    fundamentos_gerais.extend(calc["fundamentos"])

    aliq_ibs = calc["aliquota_ibs"]
    aliq_cbs = calc["aliquota_cbs"]

    # -------------------------
    # Flags especiais
    # -------------------------
    aplicar_is = should_apply_is(data_emissao, categoria)

    if compra_gov:
        fundamentos_gerais.append({
            "regra": "COMPRA GOVERNAMENTAL",
            "motivo": "Operação identificada como compra governamental",
            "fonte": "Entrada da API"
        })

    # -------------------------
    # Confiança
    # -------------------------
    confianca = 0.6
    if row:
        confianca += 0.2
    if cod_cclastrib != "REGRA-GERAL":
        confianca += 0.2
    confianca = min(confianca, 1.0)

    # -------------------------
    # Retorno final
    # -------------------------
    return {
        "categoria": categoria,
        "cclastrib": {
            "codigo": cod_cclastrib,
            "descricao": desc_cclastrib
        },
        "ibs": {
            "aliquota": aliq_ibs
        },
        "cbs": {
            "aliquota": aliq_cbs
        },
        "cst_ibs_cbs": cst_ibs_cbs,
        "cclass_trib": cclass_trib,
        "confianca": confianca,
        "alertas": alertas,
        "pendencias": pendencias,
        "fundamentos_gerais": fundamentos_gerais,
        "flags": {
            "compra_gov": compra_gov,
            "ind_doacao": ind_doacao,
            "aplicar_is": aplicar_is,
        },
    }

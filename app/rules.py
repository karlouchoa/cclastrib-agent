from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple
import unicodedata


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

def parse_date_br(value: Any) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None


def today_if_none(d: Optional[date]) -> date:
    return d if d else date.today()


def normalize_text(value: str) -> str:
    """
    Remove acentos/maiúsculas para facilitar match textual.
    """
    txt = unicodedata.normalize("NFKD", value or "").lower()
    return "".join(ch for ch in txt if not unicodedata.combining(ch))


# -------------------------
# Leitura CSV (separador ;)
# -------------------------
def read_csv_semicolon(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    encodings = ["utf-8-sig", "cp1252"]
    last_error = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = []
                for r in reader:
                    rows.append({
                        k.strip().replace("\ufeff", ""): (v.strip() if isinstance(v, str) else v)
                        for k, v in r.items()
                    })
                return rows
        except UnicodeDecodeError as e:
            last_error = e
            continue
    # If all decodes fail, raise the last error for visibility
    if last_error:
        raise last_error
    return []


# -------------------------
# Data sources (carregados do /data/anexos)
# -------------------------
@dataclass
class DataSources:
    base_dir: str
    ncm_master: List[Dict[str, str]]
    ncm_excecoes: List[Dict[str, str]]
    ncm_oficial: List[Dict[str, str]]
    ibs_aliquotas: List[Dict[str, str]]
    cbs_aliquotas: List[Dict[str, str]]
    transicao_ibs: List[Dict[str, str]]
    transicao_cbs: List[Dict[str, str]]
    cclastrib: List[Dict[str, str]]
    cst_ibs_cbs_map: List[Dict[str, str]]
    cfop_map: Dict[str, Dict[str, str]]
    ncm_beneficiados_zfm: List[Dict[str, str]]

    # modelos de anexos (ex: essenciais, alimentos in natura, agro, medicos, etc.)
    anexos_models: Dict[str, List[Dict[str, str]]]


def build_cfop_index(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for r in rows:
        code = norm_code(r.get("CFOP") or r.get("cfop") or "")
        if code:
            index[code] = r
    return index


def detect_producao_emitente(cfop_code: str, cfop_row: Optional[Dict[str, str]]) -> Optional[bool]:
    """
    True  -> CFOP de saída indicando produção do próprio estabelecimento.
    False -> CFOP válido mas sem indício de produção própria (ou entradas).
    None  -> CFOP não encontrado.
    """
    if not cfop_row:
        return None

    desc = (
        cfop_row.get("DESCRICAO_CFOP")
        or cfop_row.get("DESCRIÇÃO_CFOP")
        or cfop_row.get("descricao_cfop")
        or ""
    )

    cfop_norm = norm_code(cfop_code)
    if not cfop_norm:
        return None

    # Entradas/prestações não indicam produção do emitente (1xxx/2xxx/3xxx)
    if cfop_norm[0] not in ("5", "6", "7"):
        return False

    desc_norm = normalize_text(desc)
    keywords = [
        "producao do estabelecimento",
        "producao propria",
        "produto de fabricacao do estabelecimento",
        "industrializado pelo proprio estabelecimento",
        "venda de producao do estabelecimento",
        "remessa de producao do estabelecimento",
        "devolucao de producao do estabelecimento",
        "retorno de mercadoria de producao do estabelecimento",
    ]

    return any(k in desc_norm for k in keywords)


def detect_venda_industrializada(cfop_code: str, cfop_row: Optional[Dict[str, str]]) -> Optional[bool]:
    """
    Detecta CFOPs de venda de produtos industrializados pelo estabelecimento.
    """
    if not cfop_row:
        return None

    cfop_norm = norm_code(cfop_code)
    if not cfop_norm or cfop_norm[0] not in ("5", "6", "7"):
        return False

    desc = (
        cfop_row.get("DESCRICAO_CFOP")
        or cfop_row.get("DESCRIÇÃO_CFOP")
        or cfop_row.get("descricao_cfop")
        or ""
    )
    desc_norm = normalize_text(desc)

    keywords = [
        "venda de producao do estabelecimento",
        "venda de produto industrializado",
        "produto industrializado",
        "industrializacao propria",
        "producao do estabelecimento",
    ]

    return any(k in desc_norm for k in keywords)


def is_ncm_beneficiado_zfm(sources: DataSources, ncm_digits: str) -> bool:
    for r in sources.ncm_beneficiados_zfm:
        raw = r.get("ncm") or r.get("NCM") or ""
        if norm_ncm(raw)[:8] == ncm_digits[:8]:
            return True
    return False


def load_sources(data_anexos_dir: str) -> DataSources:
    def p(name: str) -> str:
        return os.path.join(data_anexos_dir, name)

    anexos_models: Dict[str, List[Dict[str, str]]] = {}
    # tudo que terminar com _model.csv vira "modelo"
    for fname in os.listdir(data_anexos_dir):
        if fname.lower().endswith("_model.csv"):
            anexos_models[fname] = read_csv_semicolon(p(fname))

    cfop_rows = read_csv_semicolon(p("cfop.csv"))
    cfop_index = build_cfop_index(cfop_rows)
    ncm_beneficiados_zfm = read_csv_semicolon(p("ncm_beneficiados_zfm.csv"))

    return DataSources(
        base_dir=data_anexos_dir,
        ncm_master=read_csv_semicolon(p("ncm_master.csv")),
        ncm_excecoes=read_csv_semicolon(p("ncm_excecoes.csv")),
        ncm_oficial=read_csv_semicolon(p("Tabela_NCM_Vigente_20251227.csv")),
        ibs_aliquotas=read_csv_semicolon(p("ibs_aliquotas.csv")),
        cbs_aliquotas=read_csv_semicolon(p("cbs_aliquotas.csv")),
        transicao_ibs=read_csv_semicolon(p("transicao_ibs.csv")),
        transicao_cbs=read_csv_semicolon(p("transicao_cbs.csv")),
        cclastrib=read_csv_semicolon(p("cclastrib.csv")),
        cst_ibs_cbs_map=read_csv_semicolon(p("cst_ibs_cbs_map.csv")),
        cfop_map=cfop_index,
        ncm_beneficiados_zfm=ncm_beneficiados_zfm,
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


def find_in_oficial(
    sources: DataSources,
    ncm_digits: str,
    data_emissao: date,
) -> Optional[Dict[str, str]]:
    """
    Busca na tabela oficial de NCM (vigente) para obter descrição/vigência.
    Não atribui categoria, apenas auxilia na confirmação do código.
    """
    def pick(r: Dict[str, str], keys: List[str]) -> Optional[str]:
        for k in keys:
            if k in r:
                return r.get(k)
        return None

    for r in sources.ncm_oficial:
        raw = pick(r, ["Código", "Codigo", "CÓDIGO", "CODIGO", "Cód.", "C¢digo"])
        if not raw:
            continue

        if norm_ncm(raw)[:8] != ncm_digits[:8]:
            continue

        ini = parse_date_br(
            pick(r, ["Data Início", "Data Inicio", "Data In¡cio", "Data Inicio ", "DATA INICIO", "Data Início "])
        )
        fim = parse_date_br(
            pick(r, ["Data Fim", "DATA FIM", "Data Fim "])
        )

        if ini and data_emissao < ini:
            continue
        if fim and data_emissao > fim:
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

def pick_cclastrib(
    sources: DataSources,
    regime: str,
    cfop: str,
    uf_e: str,
    uf_d: str,
    cst_icms: str,
    zfm_context: bool = False,
) -> Tuple[str, str, List[Dict[str, str]]]:
    """
    cclastrib.csv deve ser sua tabela de "classificação" operacional.
    Esperamos colunas aproximadas:
      codigo;descricao;regime_emitente;cfop;uf_origem;uf_destino;cst_icms;...
    Você pode ir enriquecendo depois.
    """
    regime = norm_code(regime)
    cfop = norm_code(cfop)
    uf_e = norm_code(uf_e)
    uf_d = norm_code(uf_d)
    cst_icms = norm_code(cst_icms)

    candidatos = []
    for r in sources.cclastrib:
        aplica_zfm = norm_code(r.get("aplica_zfm") or r.get("apply_zfm") or "")
        aplica_zfm_flag = aplica_zfm in ("S", "SIM", "1", "TRUE", "T", "Y")

        # Evita selecionar regras marcadas para ZFM quando o contexto não é ZFM
        if aplica_zfm_flag and not zfm_context:
            continue

        r_reg = norm_code(r.get("regime_emitente") or r.get("regime") or r.get("regime_fiscal") or "")
        r_cfop = norm_code(r.get("cfop") or "")
        r_ufe = norm_code(r.get("uf_origem") or r.get("uf_emitente") or "")
        r_ufd = norm_code(r.get("uf_destino") or r.get("uf_destinatario") or "")
        r_cst = norm_code(r.get("cst_icms") or "")

        # match flexível: se a célula vier vazia, vira "coringa"
        ok = True
        if r_reg and r_reg != "*" and r_reg != regime:
            ok = False
        if r_cfop and r_cfop != "*" and r_cfop != cfop:
            ok = False
        if r_ufe and r_ufe != "*" and r_ufe != uf_e:
            ok = False
        if r_ufd:
            if r_ufd == "!":
                # "!" significa UF de destino diferente da UF de origem
                if uf_d == uf_e:
                    ok = False
            elif r_ufd != "*" and r_ufd != uf_d:
                ok = False
        if r_cst and r_cst != "*" and r_cst != cst_icms:
            ok = False

        if ok:
            candidatos.append(r)

    # prioriza o mais "específico" (mais campos preenchidos)
    def score(r: Dict[str, str]) -> int:
        aplica_zfm_local = norm_code(r.get("aplica_zfm") or r.get("apply_zfm") or "")
        aplica_zfm_flag_local = aplica_zfm_local in ("S", "SIM", "1", "TRUE", "T", "Y")
        keys = [
            "regime_emitente",
            "regime",
            "regime_fiscal",
            "cfop",
            "uf_origem",
            "uf_emitente",
            "uf_destino",
            "uf_destinatario",
            "cst_icms",
        ]
        base_score = sum(1 for k in keys if (r.get(k) or "").strip() and (r.get(k) or "").strip() != "*")
        # favorece regras específicas para ZFM quando o contexto for ZFM
        if zfm_context and aplica_zfm_flag_local:
            base_score += 10
        return base_score

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
    produzido_zfm: bool,
    emitente_zfm: bool,
    destinatario_zfm: bool,
    cadastro_suframa_emitente: Optional[str],
    cadastro_suframa_emitente_ativo: Optional[bool],
    cadastro_suframa_destinatario: Optional[str],
    cadastro_suframa_destinatario_ativo: Optional[bool],
    cod_municipio_destinatario: Optional[int] = None,
) -> Dict[str, Any]:

    fundamentos_gerais: List[Dict[str, str]] = []
    alertas: List[str] = []
    pendencias: List[str] = []

    cfop_code = norm_code(cfop)
    cfop_row = sources.cfop_map.get(cfop_code)
    produzido_emitente = detect_producao_emitente(cfop_code, cfop_row)
    cfop_venda_industrializado = detect_venda_industrializada(cfop_code, cfop_row)

    if cfop_row:
        desc_cfop = (
            cfop_row.get("DESCRICAO_CFOP")
            or cfop_row.get("DESCRIÇÃO_CFOP")
            or cfop_row.get("descricao_cfop")
            or ""
        )
        motivo_cfop = f"{cfop_code} - {desc_cfop}".strip()
        if produzido_emitente is True:
            motivo_cfop = f"{motivo_cfop} (produção do emitente)"
        fundamentos_gerais.append({
            "regra": "CFOP",
            "motivo": motivo_cfop,
            "fonte": "cfop.csv"
        })
        if cfop_venda_industrializado:
            fundamentos_gerais.append({
                "regra": "CFOP INDUSTRIALIZADO",
                "motivo": f"{cfop_code} indica venda de produto industrializado pelo emitente",
                "fonte": "cfop.csv"
            })
    elif cfop_code:
        fundamentos_gerais.append({
            "regra": "CFOP",
            "motivo": f"CFOP {cfop_code} não encontrado em cfop.csv",
            "fonte": "cfop.csv"
        })

    # -------------------------
    # ZFM / SUFRAMA (emitente e destinatário)
    # -------------------------
    if emitente_zfm:
        fundamentos_gerais.append({
            "regra": "ZFM EMITENTE",
            "motivo": f"Emitente localizado em área de ZFM/ALC (UF {uf_emit})",
            "fonte": "Entrada da API"
        })
    if destinatario_zfm:
        fundamentos_gerais.append({
            "regra": "ZFM DESTINATÁRIO",
            "motivo": f"Destinatário localizado em área de ZFM/ALC (UF {uf_dest}{f', cMun {cod_municipio_destinatario}' if cod_municipio_destinatario else ''})",
            "fonte": "Entrada da API"
        })

    suf_emit = (cadastro_suframa_emitente or "").strip()
    suf_dest = (cadastro_suframa_destinatario or "").strip()

    if not suf_emit:
        pendencias.append("Cadastro SUFRAMA do emitente não informado")
    else:
        fundamentos_gerais.append({
            "regra": "SUFRAMA EMITENTE",
            "motivo": f"Cadastro {suf_emit} informado; ativo={cadastro_suframa_emitente_ativo}",
            "fonte": "Entrada da API"
        })
        if cadastro_suframa_emitente_ativo is False:
            alertas.append("Cadastro SUFRAMA do emitente informado como inativo")

    if not suf_dest:
        pendencias.append("Cadastro SUFRAMA do destinatário não informado")
    else:
        fundamentos_gerais.append({
            "regra": "SUFRAMA DESTINATÁRIO",
            "motivo": f"Cadastro {suf_dest} informado; ativo={cadastro_suframa_destinatario_ativo}",
            "fonte": "Entrada da API"
        })
        if cadastro_suframa_destinatario_ativo is False:
            alertas.append("Cadastro SUFRAMA do destinatário informado como inativo")

    # -------------------------
    # NCM / Categoria / Benefícios ZFM
    # -------------------------
    ncm_digits = norm_ncm(ncm)
    ncm_beneficiado_zfm = is_ncm_beneficiado_zfm(sources, ncm_digits)

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

    row = (
        find_excecao(sources, ncm_digits, data_emissao)
        or find_in_master(sources, ncm_digits, data_emissao)
    )
    row_oficial = None if row else find_in_oficial(sources, ncm_digits, data_emissao)

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
    elif row_oficial:
        desc = (
            row_oficial.get("Descrição")
            or row_oficial.get("Descriçao")
            or row_oficial.get("DescriÇao")
            or row_oficial.get("Descri‡Æo")
            or row_oficial.get("Descrição ")
            or ""
        )
        fundamentos_gerais.append({
            "regra": "NCM OFICIAL (vigência confirmada)",
            "motivo": f"NCM encontrado em Tabela_NCM_Vigente_20251227.csv. Descrição: {desc or 'não informada'}",
            "fonte": "Tabela_NCM_Vigente_20251227.csv"
        })
        pendencias.append(
            f"NCM {ncm_digits} encontrado na tabela oficial, mas sem categoria interna; aplicada regra geral."
        )
        alertas.append(
            "Tributação aplicada pela regra geral (fallback)"
        )
    else:
        pendencias.append(
            f"NCM {ncm_digits} não encontrado em ncm_master/ncm_excecoes nem na tabela oficial"
        )
        alertas.append(
            "Tributação aplicada pela regra geral (fallback)"
        )

    if ncm_beneficiado_zfm:
        fundamentos_gerais.append({
            "regra": "NCM BENEFÍCIO ZFM",
            "motivo": f"NCM {ncm_digits} listado para benefício de IBS na ZFM",
            "fonte": "ncm_beneficiados_zfm.csv"
        })


    # -------------------------
    # cClasTrib operacional
    # -------------------------
    zfm_context = (
        emitente_zfm
        and cadastro_suframa_emitente_ativo is True
        and produzido_zfm
        and ncm_beneficiado_zfm
    )

    cod_cclastrib, desc_cclastrib, candidatos_cclastrib = pick_cclastrib(
        sources, regime, cfop, uf_emit, uf_dest, cst_icms, zfm_context=zfm_context
    )

    # fallback seguro para produção própria (CFOP 5101/6101) se não houver match no CSV
    if cod_cclastrib == "REGRA-GERAL" and produzido_emitente:
        if cfop_code == "5101":
            cod_cclastrib = "VDA-PROPRIA-INTRA"
            desc_cclastrib = "Venda de produção do estabelecimento (interna)"
        elif cfop_code == "6101":
            cod_cclastrib = "VDA-PROPRIA-INTER"
            desc_cclastrib = "Venda de produção do estabelecimento (interestadual)"

    fundamentos_gerais.append({
        "regra": "cClasTrib",
        "motivo": f"Selecionado {cod_cclastrib}",
        "fonte": "cclastrib.csv"
    })

    # -------------------------
    # CST / cClassTrib IBS-CBS
    # -------------------------
    # Tenta mapear primeiro por cclastrib (CSV dedicado); cai para o fallback por categoria se não houver entrada.
    cst_ibs_cbs, cclass_trib, desc_cst = map_cst_ibs_cbs_from_cclastrib(
        sources,
        cod_cclastrib
    )
    fonte_cst = "cst_ibs_cbs_map.csv"

    if not cst_ibs_cbs or not cclass_trib:
        cst_ibs_cbs, cclass_trib = map_cst_ibs_cbs_from_categoria(
            categoria or "GERAL"
        )
        desc_cst = None
        fonte_cst = "fallback categoria (map_cst_ibs_cbs_from_categoria)"

    fundamentos_gerais.append({
        "regra": "CST IBS/CBS",
        "motivo": f"CST={cst_ibs_cbs} cClassTrib={cclass_trib}" + (f" ({desc_cst})" if desc_cst else ""),
        "fonte": fonte_cst
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

    beneficio_zfm_valido = zfm_context

    if beneficio_zfm_valido:
        aliq_ibs = 0.0

        selected_row = candidatos_cclastrib[0] if candidatos_cclastrib else None
        aplica_zfm_selected = False
        if selected_row:
            aplica_zfm_val = norm_code(selected_row.get("aplica_zfm") or selected_row.get("apply_zfm") or "")
            aplica_zfm_selected = aplica_zfm_val in ("S", "SIM", "1", "TRUE", "T", "Y")

        if not aplica_zfm_selected:
            # fallback seguro se não houver regra ZFM no CSV
            cod_cclastrib = "020003"
            desc_cclastrib = "ZFM - Produção própria com benefício fiscal (LC 214/2025)"

        fundamentos_gerais.append({
            "regra": "LC 214/2025 (Capítulo ZFM, arts. 439-446)",
            "motivo": "Emitente em ZFM com SUFRAMA ativa, item produzido na ZFM e NCM listado para benefício: IBS zerado.",
            "fonte": "lc214_2025.html / entrada da API / ncm_beneficiados_zfm.csv"
        })
        fundamentos_gerais.append({
            "regra": "cClasTrib ZFM",
            "motivo": f"Aplicado código {cod_cclastrib} (produção própria beneficiada na ZFM)",
            "fonte": "cclastrib.csv"
        })
    elif emitente_zfm and produzido_zfm and not ncm_beneficiado_zfm:
        alertas.append("NCM não listado para benefício ZFM; IBS calculado normalmente")

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
        "cfop_venda_industrializado": cfop_venda_industrializado,
        "emitente_zfm": emitente_zfm,
        "destinatario_zfm": destinatario_zfm,
        "cadastro_suframa_emitente": suf_emit or None,
        "cadastro_suframa_emitente_ativo": cadastro_suframa_emitente_ativo,
        "cadastro_suframa_destinatario": suf_dest or None,
        "cadastro_suframa_destinatario_ativo": cadastro_suframa_destinatario_ativo,
        "produzido_emitente": produzido_emitente,
        "beneficio_zfm_ibs_zero": beneficio_zfm_valido,
        "ncm_beneficiado_zfm": ncm_beneficiado_zfm,
        "confianca": confianca,
        "alertas": alertas,
        "pendencias": pendencias,
        "fundamentos_gerais": fundamentos_gerais,
        "flags": {
            "compra_gov": compra_gov,
            "ind_doacao": ind_doacao,
            "aplicar_is": aplicar_is,
            "produzido_zfm": produzido_zfm,
            "beneficio_zfm_ibs_zero": beneficio_zfm_valido,
        },
    }

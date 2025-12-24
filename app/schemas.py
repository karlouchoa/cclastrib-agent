from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

print(">>> ProdutoTags carregado de:", __file__)

# -------------------------
# INPUT (o que o Delphi envia)
# -------------------------
class ClassifyRequest(BaseModel):
    ano_emissao: int
    data_emissao: Optional[date] = None
    regime_fiscal_emitente: str = Field(..., description="Ex: SN, RPA, etc.")
    cfop: str = Field(..., description="CFOP da operação (ex: 5102, 6102)")
    uf_emitente: str = Field(..., min_length=2, max_length=2)
    uf_destinatario: str = Field(..., min_length=2, max_length=2)
    cst_icms: str = Field(..., description="CST ICMS usado na operação (ex: 102, 060 etc)")
    ncm: str = Field(..., description="NCM do item (pode vir com pontos)")
    valor_item: Optional[float] = Field(None, description="vItem, se você quiser cálculo de valores")
    data_emissao: Optional[date] = Field(None, description="Se não vier, usa hoje")
    cod_municipio_fg_ibs: Optional[int] = Field(None, description="cMunFGIBS (do emitente)")
    compra_governo: Optional[bool] = Field(False, description="Se a operação é compra governamental")
    ind_doacao: Optional[bool] = Field(False, description="Se é doação")
    refs_pag_antecipado: Optional[List[str]] = Field(default_factory=list, description="Lista de chaves refNFe de pagamento antecipado")
    dfe_referenciado_chave: Optional[str] = Field("", description="Chave de DF-e referenciado no item")
    dfe_referenciado_nitem: Optional[int] = Field(1, description="nItem do DF-e referenciado")


# -------------------------
# FUNDAMENTO E ALERTAS
# -------------------------
class FundamentoItem(BaseModel):
    regra: str
    motivo: str
    fonte: Optional[str] = None  # ex: "LC 214/2025 Anexo IX", "ncm_master.csv"


class BlocoResultado(BaseModel):
    # usado para cclastrib / ibs / cbs e outros
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    aliquota: Optional[float] = None
    fundamento: List[FundamentoItem] = []


# -------------------------
# SAÍDA "PRONTA PARA XML"
# -------------------------
class IdeCompraGov(BaseModel):
    tpEnteGov: Optional[str] = None
    pRedutor: Optional[float] = None
    tpOperGov: Optional[str] = None


class IdePagAntecipado(BaseModel):
    refNFe: str


class IdeTags(BaseModel):
    dPrevEntrega: Optional[str] = None  # ISO yyyy-mm-dd
    cMunFGIBS: Optional[int] = None

    tpNFDebito: Optional[str] = None
    tpNFCredito: Optional[str] = None

    gCompraGov: Optional[IdeCompraGov] = None
    gPagAntecipado: List[IdePagAntecipado] = Field(default_factory=list)


class DFeReferenciado(BaseModel):
    chaveAcesso: Optional[str] = None
    nItem: Optional[int] = None


class ProdutoTags(BaseModel):
    indBemMovelUsado: Optional[str] = "tieNenhum"
    vItem: Optional[float] = None
    dfe_referenciado: Optional[DFeReferenciado] = None


# --------- IBS/CBS grupos (JSON espelha o que você setaria no ACBr) ----------
class IBSUFGDif(BaseModel):
    pDif: Optional[float] = None
    vDif: Optional[float] = None


class IBSUFGDevTrib(BaseModel):
    vDevTrib: Optional[float] = None


class IBSUFGRed(BaseModel):
    pRedAliq: Optional[float] = None
    pAliqEfet: Optional[float] = None


class IBSUF(BaseModel):
    pIBSUF: Optional[float] = None
    vIBSUF: Optional[float] = None
    gDif: Optional[IBSUFGDif] = None
    gDevTrib: Optional[IBSUFGDevTrib] = None
    gRed: Optional[IBSUFGRed] = None


class IBSMun(BaseModel):
    pIBSMun: Optional[float] = None
    vIBSMun: Optional[float] = None
    gDif: Optional[IBSUFGDif] = None
    gDevTrib: Optional[IBSUFGDevTrib] = None
    gRed: Optional[IBSUFGRed] = None


class CBS(BaseModel):
    pCBS: Optional[float] = None
    vCBS: Optional[float] = None
    gDif: Optional[IBSUFGDif] = None
    gDevTrib: Optional[IBSUFGDevTrib] = None
    gRed: Optional[IBSUFGRed] = None


class TribRegular(BaseModel):
    CSTReg: Optional[str] = None
    cClassTribReg: Optional[str] = None
    pAliqEfetRegIBSUF: Optional[float] = None
    vTribRegIBSUF: Optional[float] = None
    pAliqEfetRegIBSMun: Optional[float] = None
    vTribRegIBSMun: Optional[float] = None
    pAliqEfetRegCBS: Optional[float] = None
    vTribRegCBS: Optional[float] = None


class TribCompraGov(BaseModel):
    pAliqIBSUF: Optional[float] = None
    vTribIBSUF: Optional[float] = None
    pAliqIBSMun: Optional[float] = None
    vTribIBSMun: Optional[float] = None
    pAliqCBS: Optional[float] = None
    vTribCBS: Optional[float] = None


class GIBSCBS(BaseModel):
    vBC: Optional[float] = None
    gIBSUF: Optional[IBSUF] = None
    gIBSMun: Optional[IBSMun] = None
    vIBS: Optional[float] = None
    gCBS: Optional[CBS] = None
    gTribRegular: Optional[TribRegular] = None
    gTribCompraGov: Optional[TribCompraGov] = None


class MonoPadrao(BaseModel):
    qBCMono: Optional[float] = None
    adRemIBS: Optional[float] = None
    adRemCBS: Optional[float] = None
    vIBSMono: Optional[float] = None
    vCBSMono: Optional[float] = None


class MonoReten(BaseModel):
    qBCMonoReten: Optional[float] = None
    adRemIBSReten: Optional[float] = None
    vIBSMonoReten: Optional[float] = None
    vCBSMonoReten: Optional[float] = None


class MonoRet(BaseModel):
    qBCMonoRet: Optional[float] = None
    adRemIBSRet: Optional[float] = None
    vIBSMonoRet: Optional[float] = None
    vCBSMonoRet: Optional[float] = None


class MonoDif(BaseModel):
    pDifIBS: Optional[float] = None
    vIBSMonoDif: Optional[float] = None
    pDifCBS: Optional[float] = None
    vCBSMonoDif: Optional[float] = None


class GIBSCBSMono(BaseModel):
    gMonoPadrao: Optional[MonoPadrao] = None
    gMonoReten: Optional[MonoReten] = None
    gMonoRet: Optional[MonoRet] = None
    gMonoDif: Optional[MonoDif] = None
    vTotIBSMonoItem: Optional[float] = None
    vTotCBSMonoItem: Optional[float] = None


class GTransfCred(BaseModel):
    vIBS: Optional[float] = None
    vCBS: Optional[float] = None


class GAjusteCompet(BaseModel):
    competApur: Optional[str] = None
    vIBS: Optional[float] = None
    vCBS: Optional[float] = None


class GEstornoCred(BaseModel):
    vIBSEstCred: Optional[float] = None
    vCBSEstCred: Optional[float] = None


class CredPresOperIBS(BaseModel):
    pCredPres: Optional[float] = None
    vCredPres: Optional[float] = None
    vCredPresCondSus: Optional[float] = None


class CredPresOperCBS(BaseModel):
    pCredPres: Optional[float] = None
    vCredPres: Optional[float] = None
    vCredPresCondSus: Optional[float] = None


class GCredPresOper(BaseModel):
    cCredPres: Optional[str] = "cpNenhum"
    vBCCredPres: Optional[float] = None
    gIBSCredPres: Optional[CredPresOperIBS] = None
    gCBSCredPres: Optional[CredPresOperCBS] = None


class GCredPresIBSZFM(BaseModel):
    competApur: Optional[str] = None
    tpCredPresIBSZFM: Optional[str] = None
    vCredPresIBSZFM: Optional[float] = None


class IBSCBSTags(BaseModel):
    CST: Optional[str] = None
    cClassTrib: Optional[str] = None
    indDoacao: Optional[str] = None  # tieSim/tieNao
    gIBSCBS: Optional[GIBSCBS] = None
    gIBSCBSMono: Optional[GIBSCBSMono] = None
    gTransfCred: Optional[GTransfCred] = None
    gAjusteCompet: Optional[GAjusteCompet] = None
    gEstornoCred: Optional[GEstornoCred] = None
    gCredPresOper: Optional[GCredPresOper] = None
    gCredPresIBSZFM: Optional[GCredPresIBSZFM] = None


class ISTags(BaseModel):
    # só se aplicável (ex: a partir de 2027 e produto nocivo)
    CSTIS: Optional[str] = None
    cClassTribIS: Optional[str] = None
    vBCIS: Optional[float] = None
    pIS: Optional[float] = None
    pISEspec: Optional[float] = None
    uTrib: Optional[str] = None
    qTrib: Optional[float] = None
    vIS: Optional[float] = None


class ImpostoTags(BaseModel):
    isel: Optional[ISTags] = None
    ibscbs: Optional[IBSCBSTags] = None


class TotaisIBS(BaseModel):
    vIBS: Optional[float] = None
    vCredPres: Optional[float] = None
    vCredPresCondSus: Optional[float] = None
    gIBSUFTot: Optional[Dict[str, Any]] = None
    gIBSMunTot: Optional[Dict[str, Any]] = None


class TotaisCBS(BaseModel):
    vDif: Optional[float] = None
    vDevTrib: Optional[float] = None
    vCBS: Optional[float] = None
    vCredPres: Optional[float] = None
    vCredPresCondSus: Optional[float] = None


class TotaisMono(BaseModel):
    vIBSMono: Optional[float] = None
    vCBSMono: Optional[float] = None
    vIBSMonoReten: Optional[float] = None
    vCBSMonoReten: Optional[float] = None
    vIBSMonoRet: Optional[float] = None
    vCBSMonoRet: Optional[float] = None


class TotaisEstorno(BaseModel):
    vIBSEstCred: Optional[float] = None
    vCBSEstCred: Optional[float] = None


class IBSCBSTotTags(BaseModel):
    vBCIBSCBS: Optional[float] = None
    gIBS: Optional[TotaisIBS] = None
    gCBS: Optional[TotaisCBS] = None
    gMono: Optional[TotaisMono] = None
    gEstornoCred: Optional[TotaisEstorno] = None


class TotaisTags(BaseModel):
    isTot_vIS: Optional[float] = None
    ibscbsTot: Optional[IBSCBSTotTags] = None
    vNFTot: Optional[float] = None


class XmlPayload(BaseModel):
    ide: IdeTags
    produto: ProdutoTags
    imposto: ImpostoTags
    totais: TotaisTags


# -------------------------
# RESPOSTA DA API
# -------------------------
class ClassifyResponse(BaseModel):
    cclastrib: BlocoResultado
    ibs: BlocoResultado
    cbs: BlocoResultado
    cst_ibs_cbs: str          # ex: "000"
    cclass_trib: str          # ex: "000001"

    confianca: float
    alertas: List[str]
    pendencias: List[str]
    xml: XmlPayload
    fundamentos_gerais: List[FundamentoItem]

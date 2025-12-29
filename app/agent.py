from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from .schemas import ClassifyLoteRequest, ClassifyLoteResponse, ClassifyLoteItemResponse

from .schemas import (
    ClassifyRequest,
    ClassifyResponse,
    FundamentoItem,
    BlocoResultado,
    XmlPayload,
    IdeTags,
    IdeCompraGov,
    IdePagAntecipado,
    ProdutoTags,
    DFeReferenciado,
    ImpostoTags,
    IBSCBSTags,
    GIBSCBS,
    IBSUF,
    IBSMun,
    CBS,
    TotaisTags,
    IBSCBSTotTags,
    TotaisIBS,
    TotaisCBS,
    TotaisMono,
    TotaisEstorno,
    ISTags,
)
from .rules import load_sources, classify, norm_ncm
from .cache import TTLCache, make_cache_key


class CClastribAgent:
    def __init__(self, data_anexos_dir: str, cache_ttl_seconds: int = 3600):
        self.data_anexos_dir = data_anexos_dir
        self._cache = TTLCache(default_ttl_seconds=cache_ttl_seconds)
        self._sources = load_sources(data_anexos_dir)

    def reload_sources(self) -> None:
        self._sources = load_sources(self.data_anexos_dir)
        self._cache.clear()

    def handle(self, req: ClassifyRequest) -> ClassifyResponse:
        # Se você manda ano_emissao, use ele SEMPRE
        # Data de emissão SEMPRE vem do ano_emissao
        if req.ano_emissao:
            data_emissao = date(int(req.ano_emissao), 1, 1)
        else:
            data_emissao = date.today()

        ncm_digits = norm_ncm(req.ncm)
        produzido_zfm = (req.produzido_zfm or "").strip().upper() == "S"
        emitente_zfm = (req.emitente_zona_franca_manaus or "").strip().upper() == "S"
        destinatario_zfm = (req.destinatario_zona_franca_manaus or "").strip().upper() == "S"

        cadastro_suframa_emitente = (req.cadastro_suframa_emitente or "").strip()
        cadastro_suframa_destinatario = (req.cadastro_suframa_destinatario or "").strip()

        def parse_sn(value: Optional[str]) -> Optional[bool]:
            if value is None:
                return None
            if isinstance(value, bool):
                return value
            return str(value).strip().upper() == "S"

        cadastro_suframa_emitente_ativo = parse_sn(req.cadastro_suframa_emitente_ativo)
        cadastro_suframa_destinatario_ativo = parse_sn(req.cadastro_suframa_destinatario_ativo)

        def round_money(v):
            if v is None:
                return None
            return round(float(v), 2)

        cache_key = make_cache_key(
            req.regime_fiscal_emitente,
            req.cfop,
            req.uf_emitente,
            req.uf_destinatario,
            req.cst_icms,
            ncm_digits,
            data_emissao.isoformat(),
            "GOV" if req.compra_governo else "NOGOV",
            "DOA" if req.ind_doacao else "NODOA",
            "ZFM" if produzido_zfm else "NOZFM",
            "EZFM" if emitente_zfm else "NOEZFM",
            "DZFM" if destinatario_zfm else "NODZFM",
            f"SUFE_{'P' if cadastro_suframa_emitente else 'NP'}_{'AT' if cadastro_suframa_emitente_ativo else 'IN' if cadastro_suframa_emitente_ativo is False else 'NA'}",
            f"SUFD_{'P' if cadastro_suframa_destinatario else 'NP'}_{'AT' if cadastro_suframa_destinatario_ativo else 'IN' if cadastro_suframa_destinatario_ativo is False else 'NA'}",
        )

        cached = self._cache.get(cache_key)
        if cached:
            return cached

        result = classify(
            self._sources,
            regime=req.regime_fiscal_emitente,
            cfop=req.cfop,
            uf_emit=req.uf_emitente,
            uf_dest=req.uf_destinatario,
            cst_icms=req.cst_icms,
            ncm=req.ncm,
            data_emissao=data_emissao,
            compra_gov=bool(req.compra_governo),
            ind_doacao=bool(req.ind_doacao),
            produzido_zfm=produzido_zfm,
            emitente_zfm=emitente_zfm,
            destinatario_zfm=destinatario_zfm,
            cadastro_suframa_emitente=cadastro_suframa_emitente,
            cadastro_suframa_emitente_ativo=cadastro_suframa_emitente_ativo,
            cadastro_suframa_destinatario=cadastro_suframa_destinatario,
            cadastro_suframa_destinatario_ativo=cadastro_suframa_destinatario_ativo,
            cod_municipio_destinatario=req.cod_municipio_destinatario,
        )

        # -------------------------
        # Monta fundamentos estruturados
        # -------------------------
        fundamentos_gerais = [
            FundamentoItem(**f) for f in result.get("fundamentos_gerais", [])
        ]

        cclastrib = BlocoResultado(
            codigo=result["cclastrib"]["codigo"],
            descricao=result["cclastrib"]["descricao"],
            fundamento=[
                FundamentoItem(
                    regra="LC 214/2025",
                    motivo="Classificação operacional baseada em regime/CFOP/UF/CST e tabelas internas",
                    fonte="cclastrib.csv",
                )
            ],
        )

        ibs = BlocoResultado(
            aliquota=result["ibs"]["aliquota"],
            fundamento=[
                FundamentoItem(
                    regra="LC 214/2025",
                    motivo="Alíquota IBS calculada pela transição (percentual_ibs) + reduções por NCM/categoria",
                    fonte="transicao_ibs.csv / ncm_master.csv",
                )
            ],
        )

        cbs = BlocoResultado(
            aliquota=result["cbs"]["aliquota"],
            fundamento=[
                FundamentoItem(
                    regra="LC 214/2025",
                    motivo="Alíquota CBS calculada por alíquota base + transição + reduções por NCM/categoria",
                    fonte="transicao_cbs.csv / ncm_master.csv",
                )
            ],
        )

        # -------------------------
        # Monta payload "XML"
        # -------------------------
        beneficio_zfm_ibs_zero = bool(result.get("beneficio_zfm_ibs_zero"))
        tp_nf_debito = "tdNenhum" if beneficio_zfm_ibs_zero else "tdIntegral"

        ide = IdeTags(
            dPrevEntrega=(data_emissao + timedelta(days=10)).isoformat(),
            cMunFGIBS=req.cod_municipio_fg_ibs,
            tpNFDebito=tp_nf_debito,
            tpNFCredito="tcNenhum",
            gCompraGov=(
                IdeCompraGov(tpEnteGov="tcgEstados", pRedutor=5, tpOperGov="togFornecimento")
                if req.compra_governo
                else None
            ),
            gPagAntecipado=[IdePagAntecipado(refNFe=x) for x in (req.refs_pag_antecipado or [])],
        )

        dfe_ref = None
        ch = (req.dfe_referenciado_chave or "").strip()
        if ch:
            dfe_ref = DFeReferenciado(
                chaveAcesso=ch,
                nItem=req.dfe_referenciado_nitem or 1,
            )

        produto = ProdutoTags(
            indBemMovelUsado="tieNenhum",
            vItem=round_money(req.valor_item),
            DFeReferenciado=dfe_ref,
        )

        # IBS/CBS: preenche CST/cClassTrib e alíquotas em gIBSCBS
        cst_ibs_cbs = result.get("cst_ibs_cbs")
        cclass_trib = result.get("cclass_trib")

        ind_doacao_tag = "tieSim" if req.ind_doacao else "tieNao"

        # Base de cálculo e valores (se valor_item vier)
        vbc = float(req.valor_item) if req.valor_item is not None else None
        vbc = round_money(vbc)
        p_ibs = float(result["ibs"]["aliquota"]) * 100.0 if result["ibs"]["aliquota"] is not None else None
        p_cbs = float(result["cbs"]["aliquota"]) * 100.0 if result["cbs"]["aliquota"] is not None else None

        v_ibs = (vbc * (p_ibs / 100.0)) if (vbc is not None and p_ibs is not None) else None
        v_cbs = (vbc * (p_cbs / 100.0)) if (vbc is not None and p_cbs is not None) else None
        v_ibs = round_money(v_ibs)
        v_cbs = round_money(v_cbs)

        total_debito = sum(
            v for v in [v_ibs, v_cbs]
            if v is not None
        ) if (v_ibs is not None or v_cbs is not None) else 0.0
        total_credito = 0.0

        g_ibscbs = GIBSCBS(
            vBC=vbc,
            gIBSUF=IBSUF(pIBSUF=p_ibs, vIBSUF=v_ibs),
            gIBSMun=IBSMun(pIBSMun=None, vIBSMun=None),
            vIBS=v_ibs,  # se você quiser dividir UF/Mun, ajuste aqui
            gCBS=CBS(pCBS=p_cbs, vCBS=v_cbs),
            gTribRegular=None,
            gTribCompraGov=None,
        )

        ibscbs_tags = IBSCBSTags(
            CST=cst_ibs_cbs,          # "000"
            cClassTrib=cclass_trib,   # "000001"
            indDoacao=ind_doacao_tag,
            gIBSCBS=g_ibscbs,
        )


        # IS (se aplicável)
        isel = None
        if result["flags"].get("aplicar_is"):
            # aqui você deverá mapear CSTIS/cClassTribIS e alíquotas por categoria/NCM quando definir isso
            isel = ISTags(
                CSTIS="cstis000",
                cClassTribIS="000001",
                vBCIS=vbc,
                pIS=5.0,
                pISEspec=5.0,
                uTrib="UNIDAD",
                qTrib=1.0,
                vIS=(vbc * 0.05) if vbc is not None else None,
            )

        imposto = ImpostoTags(isel=isel, ibscbs=ibscbs_tags)

        # Totais (mínimos coerentes)
        ibscbs_tot = IBSCBSTotTags(
            vBCIBSCBS=vbc,
            gIBS=TotaisIBS(
                vIBS=v_ibs,
                vCredPres=None,
                vCredPresCondSus=None,
                gIBSUFTot={"vDif": None, "vDevTrib": None, "vIBSUF": v_ibs},
                gIBSMunTot={"vDif": None, "vDevTrib": None, "vIBSMun": None},
            ),
            gCBS=TotaisCBS(
                vDif=None,
                vDevTrib=None,
                vCBS=v_cbs,
                vCredPres=None,
                vCredPresCondSus=None,
            ),
            gMono=TotaisMono(),
            gEstornoCred=TotaisEstorno(),
        )

        if isel:
            isel.vBCIS = round_money(isel.vBCIS)
            isel.vIS = round_money(isel.vIS)
        v_is = isel.vIS if isel else None
        v_nf_tot = None
        if vbc is not None:
            v_nf_tot = vbc
            if v_ibs is not None:
                v_nf_tot += v_ibs
            if v_cbs is not None:
                v_nf_tot += v_cbs
            if v_is is not None:
                v_nf_tot += v_is
            v_nf_tot = round_money(v_nf_tot)

        totais = TotaisTags(
            isTot_vIS=v_is,
            ibscbsTot=ibscbs_tot,
            vNFTot=v_nf_tot,
        )

        beneficio_zfm_ibs_zero = bool(result.get("beneficio_zfm_ibs_zero"))
        tp_nf_debito = "tdNenhum" if not total_debito or beneficio_zfm_ibs_zero else "tdIntegral"
        tp_nf_credito = "tcNenhum" if not total_credito else "tcIntegral"

        xml_payload = XmlPayload(
            ide=IdeTags(
                dPrevEntrega=ide.dPrevEntrega,
                cMunFGIBS=ide.cMunFGIBS,
                tpNFDebito=tp_nf_debito,
                tpNFCredito=tp_nf_credito,
                gCompraGov=ide.gCompraGov,
                gPagAntecipado=ide.gPagAntecipado,
            ),
            produto=produto,
            imposto=imposto,
            totais=totais,
        )

        resp = ClassifyResponse(
            cclastrib=cclastrib,
            ibs=ibs,
            cbs=cbs,
            cst_ibs_cbs=cst_ibs_cbs,
            cclass_trib=cclass_trib,
            cfop_venda_industrializado=result.get("cfop_venda_industrializado"),
            emitente_zfm=result.get("emitente_zfm"),
            destinatario_zfm=result.get("destinatario_zfm"),
            cadastro_suframa_emitente=result.get("cadastro_suframa_emitente"),
            cadastro_suframa_emitente_ativo=result.get("cadastro_suframa_emitente_ativo"),
            cadastro_suframa_destinatario=result.get("cadastro_suframa_destinatario"),
            cadastro_suframa_destinatario_ativo=result.get("cadastro_suframa_destinatario_ativo"),
            produzido_emitente=result.get("produzido_emitente"),
            beneficio_zfm_ibs_zero=result.get("beneficio_zfm_ibs_zero"),
            ncm_beneficiado_zfm=result.get("ncm_beneficiado_zfm"),
            total_debito=total_debito,
            total_credito=total_credito,
            confianca=result["confianca"],
            alertas=result.get("alertas", []),
            pendencias=result.get("pendencias", []),
            xml=xml_payload,
            fundamentos_gerais=fundamentos_gerais,
        )

        self._cache.set(cache_key, resp)
        return resp
    

    def handle_lote(self, req: ClassifyLoteRequest) -> ClassifyLoteResponse:
        resultados = []

        for item in req.itens:
            # Each item can have its own CFOP/CST, so use the item fields
            req_item = ClassifyRequest(
                ano_emissao=req.ano_emissao,
                regime_fiscal_emitente=req.regime_fiscal_emitente,
                cfop=item.cfop,
                uf_emitente=req.uf_emitente,
                uf_destinatario=req.uf_destinatario,
                cst_icms=item.cst_icms,
                cod_municipio_fg_ibs=req.cod_municipio_fg_ibs,
                cod_municipio_destinatario=req.cod_municipio_destinatario,
                emitente_zona_franca_manaus=req.emitente_zona_franca_manaus,
                destinatario_zona_franca_manaus=req.destinatario_zona_franca_manaus,
                cadastro_suframa_emitente=req.cadastro_suframa_emitente,
                cadastro_suframa_emitente_ativo=req.cadastro_suframa_emitente_ativo,
                cadastro_suframa_destinatario=req.cadastro_suframa_destinatario,
                cadastro_suframa_destinatario_ativo=req.cadastro_suframa_destinatario_ativo,
                compra_governo=req.compra_governo,
                ind_doacao=req.ind_doacao,
                produzido_zfm=item.produzido_zfm,
                refs_pag_antecipado=req.refs_pag_antecipado,
                ncm=item.ncm,
                valor_item=item.valor_item,
            )

            resultado = self.handle(req_item)

            resultados.append(
                ClassifyLoteItemResponse(
                    ncm=item.ncm,
                    resultado=resultado
                )
            )

        return ClassifyLoteResponse(
            ano_emissao=req.ano_emissao,
            itens=resultados
        )

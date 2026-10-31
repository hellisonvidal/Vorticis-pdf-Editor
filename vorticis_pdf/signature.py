"""Assinatura digital de PDF com certificado (padrão PAdES, compatível com ICP-Brasil).

  * Certificado A1: arquivo .pfx / .p12 com senha.
  * Certificado A3: token USB ou cartão inteligente, via driver PKCS#11 do fabricante
    (SafeNet, Watchdata, GD/Valid, Certisign, Serasa...) com PIN.
  * Assinatura visível (carimbo na área escolhida) ou invisível.
  * Carimbo do tempo opcional (servidor TSA gratuito), para comprovar a data da assinatura.
  * Verificação das assinaturas de um PDF (integridade, signatário, data, confiança).

A assinatura é gravada de forma incremental num NOVO arquivo; o original não é alterado.
Qualquer edição posterior no PDF assinado invalida a assinatura.
"""
from __future__ import annotations

import datetime as _dt
import glob
import logging
import os
import sys
from dataclasses import dataclass

for _name in ("pyhanko", "pyhanko_certvalidator", "pyhanko.sign"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

TSA_SERVERS = {
    "DigiCert (gratuito)": "http://timestamp.digicert.com",
    "Sectigo (gratuito)": "http://timestamp.sectigo.com",
    "FreeTSA (gratuito)": "https://freetsa.org/tsr",
}

# drivers PKCS#11 mais comuns de tokens/cartões usados no Brasil
PKCS11_DRIVERS = [
    ("SafeNet eToken / Gemalto", "eTPKCS11.dll"),
    ("SafeNet (IDPrime)", "IDPrimePKCS11.dll"),
    ("Watchdata (ProxKey / Certisign)", "WDPKCS.dll"),
    ("Watchdata", "SignatureP11.dll"),
    ("G&D / Valid StarSign", "aetpkss1.dll"),
    ("GD Burti / Safesign", "aetpksse.dll"),
    ("Oberthur / IDEMIA", "OcsCryptoki.dll"),
    ("Feitian / ePass", "eps2003csp11.dll"),
    ("Feitian", "ShuttleCsp11_3003.dll"),
    ("Bit4id", "bit4ipki.dll"),
    ("Taglio / Pronova", "cmP11.dll"),
    ("OpenSC (genérico)", "opensc-pkcs11.dll"),
]


def find_pkcs11_drivers() -> list[tuple[str, str]]:
    """Drivers de token/cartão instalados no computador: [(descrição, caminho)]."""
    found = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        folders = [os.path.join(windir, "System32"), os.path.join(windir, "SysWOW64"),
                   r"C:\Program Files\OpenSC Project\OpenSC\pkcs11"]
    else:
        folders = ["/usr/lib", "/usr/lib/x86_64-linux-gnu", "/usr/local/lib", "/usr/lib64"]
    for label, name in PKCS11_DRIVERS:
        for folder in folders:
            p = os.path.join(folder, name if sys.platform.startswith("win") else name.replace(".dll", ".so"))
            if os.path.isfile(p) and p not in [f[1] for f in found]:
                found.append((label, p))
    if not sys.platform.startswith("win"):
        for p in glob.glob("/usr/lib/**/opensc-pkcs11.so", recursive=True):
            if p not in [f[1] for f in found]:
                found.append(("OpenSC (genérico)", p))
    return found


# ------------------------------------------------------------------ informações do certificado
ICP_PF = "2.16.76.1.3.1"   # dados da pessoa física (nascimento + CPF ...)
ICP_PJ = "2.16.76.1.3.3"   # CNPJ
ICP_RESP = "2.16.76.1.3.2"  # nome do responsável (e-CNPJ)


@dataclass
class CertInfo:
    nome: str
    emissor: str
    validade_inicio: str
    validade_fim: str
    vencido: bool
    cpf: str = ""
    cnpj: str = ""
    email: str = ""

    def resumo(self) -> str:
        doc = f"CPF {self.cpf}" if self.cpf else (f"CNPJ {self.cnpj}" if self.cnpj else "")
        status = "⚠ VENCIDO" if self.vencido else "válido"
        return (f"{self.nome}{' — ' + doc if doc else ''}\nEmitido por: {self.emissor}\n"
                f"Validade: {self.validade_inicio} a {self.validade_fim} ({status})")


def _fmt_cpf(d):
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else d


def _fmt_cnpj(d):
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}" if len(d) == 14 else d


def cert_info(cert) -> CertInfo:
    """cert: asn1crypto.x509.Certificate"""
    import datetime as dt
    subj = cert.subject.native
    cn = subj.get("common_name", "") or cert.subject.human_friendly
    cpf = cnpj = email = ""
    # e-CPF/e-CNPJ ICP-Brasil: CN costuma ser "NOME:CPF" ou "EMPRESA:CNPJ"
    if ":" in cn:
        nome, _, num = cn.rpartition(":")
        digits = "".join(ch for ch in num if ch.isdigit())
        if len(digits) == 11:
            cpf, cn = _fmt_cpf(digits), nome
        elif len(digits) == 14:
            cnpj, cn = _fmt_cnpj(digits), nome
    try:
        san = cert.subject_alt_name_value
        for gn in (san or []):
            if gn.name == "rfc822_name":
                email = gn.native
            elif gn.name == "other_name":
                oid = gn.chosen["type_id"].dotted
                raw = gn.chosen["value"].parsed
                val = raw.native if hasattr(raw, "native") else str(raw)
                if isinstance(val, bytes):
                    val = val.decode("latin-1", "ignore")
                digits = "".join(ch for ch in str(val) if ch.isdigit())
                if oid == ICP_PF and len(digits) >= 19 and not cpf:
                    cpf = _fmt_cpf(digits[8:19])
                elif oid == ICP_PJ and len(digits) >= 14 and not cnpj:
                    cnpj = _fmt_cnpj(digits[:14])
    except Exception:
        pass
    v = cert["tbs_certificate"]["validity"]
    start, end = v["not_before"].native, v["not_after"].native
    issuer = cert.issuer.native.get("common_name", "") or cert.issuer.human_friendly
    return CertInfo(cn, issuer, start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y"),
                    end < dt.datetime.now(dt.timezone.utc), cpf, cnpj, email)


# ------------------------------------------------------------------ assinantes
def load_a1(path: str, password: str):
    """Carrega um certificado A1 (.pfx/.p12). Retorna (signer, CertInfo)."""
    from pyhanko.sign import signers
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("Arquivo do certificado não encontrado")
    signer = signers.SimpleSigner.load_pkcs12(path, passphrase=(password or "").encode("utf-8"))
    if signer is None:
        raise ValueError("Senha do certificado incorreta ou arquivo inválido")
    return signer, cert_info(signer.signing_cert)


def list_a3_certs(lib: str, pin: str) -> list[dict]:
    """Certificados disponíveis no token: [{'label', 'slot', 'info'}]."""
    import pkcs11
    from asn1crypto import x509
    lib_obj = pkcs11.lib(lib)
    out = []
    for slot in lib_obj.get_slots(token_present=True):
        token = slot.get_token()
        with token.open(user_pin=pin) as session:
            for obj in session.get_objects({pkcs11.Attribute.CLASS: pkcs11.ObjectClass.CERTIFICATE}):
                try:
                    cert = x509.Certificate.load(obj[pkcs11.Attribute.VALUE])
                    label = obj[pkcs11.Attribute.LABEL]
                except Exception:
                    continue
                out.append({"label": label, "token": token.label, "info": cert_info(cert)})
    return out


def _a3_session(lib: str, pin: str, token_label: str | None):
    from pyhanko.sign import pkcs11 as p11
    return p11.open_pkcs11_session(lib, token_label=token_label, user_pin=pin)


# ------------------------------------------------------------------ assinar
def _to_pdf_box(mediabox, rect):
    """Converte retângulo do PyMuPDF (origem no topo) para coordenadas PDF (origem embaixo)."""
    x0, y0, x1, y1 = rect
    h = mediabox[3]
    return (int(x0 + mediabox[0]), int(h - y1), int(x1 + mediabox[0]), int(h - y0))


def sign_pdf(in_path: str, out_path: str, *, a1_path=None, a1_password=None,
             a3_lib=None, a3_pin=None, a3_token=None, a3_cert_label=None,
             page_index: int = 0, rect=None, mediabox=None, reason="", location="", contact="",
             tsa_url: str | None = None, field_name: str | None = None) -> dict:
    """Assina 'in_path' gravando 'out_path'. rect=None -> assinatura invisível."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign import fields, signers, timestamps
    from pyhanko.stamp import TextStampStyle

    with open(in_path, "rb") as f:
        existing = len(list(fields.enumerate_sig_fields(PdfFileReader(f, strict=False))))
    field_name = field_name or f"Assinatura{existing + 1}"

    session = None
    if a1_path:
        signer, info = load_a1(a1_path, a1_password)
    else:
        from pyhanko.sign.pkcs11 import PKCS11Signer
        session = _a3_session(a3_lib, a3_pin, a3_token)
        signer = PKCS11Signer(session, cert_label=a3_cert_label, key_label=a3_cert_label)
        info = cert_info(signer.signing_cert)
    try:
        meta = signers.PdfSignatureMetadata(
            field_name=field_name, reason=reason or None, location=location or None,
            contact_info=contact or None, md_algorithm="sha256",
            subfilter=fields.SigSeedSubFilter.PADES, use_pades_lta=False)
        spec = None
        if rect is not None:
            spec = fields.SigFieldSpec(sig_field_name=field_name, on_page=page_index,
                                       box=_to_pdf_box(mediabox, rect))
        doc_line = f"CPF: {info.cpf}" if info.cpf else (f"CNPJ: {info.cnpj}" if info.cnpj else "")
        text = "Assinado digitalmente por:\n%(signer)s\n" + (doc_line + "\n" if doc_line else "") + \
               "Data: %(data)s" + ("\nMotivo: %(reason)s" if reason else "")
        style = TextStampStyle(stamp_text=text, border_width=1)
        local_now = _dt.datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S (UTC%z)")
        timestamper = timestamps.HTTPTimeStamper(tsa_url) if tsa_url else None
        pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper,
                                       stamp_style=style, new_field_spec=spec)
        tmp = out_path + ".tmp"
        with open(in_path, "rb") as inf:
            w = IncrementalPdfFileWriter(inf, strict=False)
            with open(tmp, "wb") as outf:
                pdf_signer.sign_pdf(w, output=outf,
                                    appearance_text_params={"signer": info.nome, "reason": reason or "",
                                                            "data": local_now})
        os.replace(tmp, out_path)
    finally:
        if session is not None:
            session.close()
    return {"arquivo": out_path, "signatario": info.nome, "cpf": info.cpf, "cnpj": info.cnpj,
            "certificado": info.resumo(), "campo": field_name, "carimbo_tempo": bool(tsa_url)}


# ------------------------------------------------------------------ verificar
def _trust_roots():
    """Certificados raiz confiáveis do Windows (inclui ICP-Brasil quando instalada)."""
    roots = []
    try:
        import ssl
        from asn1crypto import x509
        if hasattr(ssl, "enum_certificates"):
            for store in ("ROOT", "CA"):
                for der, enc, _trust in ssl.enum_certificates(store):
                    if enc == "x509_asn":
                        try:
                            roots.append(x509.Certificate.load(der))
                        except Exception:
                            pass
    except Exception:
        pass
    return roots


def verify_pdf(path: str) -> list[dict]:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    roots = _trust_roots()
    results = []
    with open(path, "rb") as f:
        reader = PdfFileReader(f, strict=False)
        for sig in reader.embedded_signatures:
            item = {"campo": sig.field_name, "signatario": "?", "data": "", "integra": False,
                    "valida": False, "confiavel": False, "cobre_documento_todo": False,
                    "detalhes": "", "carimbo_tempo": False}
            try:
                vc = ValidationContext(trust_roots=roots or None, allow_fetching=False)
                st = validate_pdf_signature(sig, vc)
                info = cert_info(st.signing_cert)
                item.update(signatario=info.nome, cpf=info.cpf, cnpj=info.cnpj, emissor=info.emissor,
                            integra=bool(st.intact), valida=bool(st.valid), confiavel=bool(st.trusted),
                            cobre_documento_todo=str(st.coverage).endswith("ENTIRE_FILE"),
                            carimbo_tempo=st.timestamp_validity is not None)
                when = st.signer_reported_dt or (st.timestamp_validity.timestamp if st.timestamp_validity else None)
                if when:
                    item["data"] = when.astimezone().strftime("%d/%m/%Y %H:%M:%S")
                item["detalhes"] = str(st.coverage).split(".")[-1]
            except Exception as e:
                item["detalhes"] = f"Erro ao validar: {e}"
            results.append(item)
    return results


def has_signatures(path: str) -> bool:
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        with open(path, "rb") as f:
            return bool(PdfFileReader(f, strict=False).embedded_signatures)
    except Exception:
        return False

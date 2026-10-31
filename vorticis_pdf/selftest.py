"""Autoteste: VorticisPDF.exe --selftest

Usado no build automático para comprovar que o programa instalado funciona num Windows
limpo. Testa abrir, editar texto sem sobrepor vizinhos, unir pela interface (fluxo que
travava na versão 1.0.0), separar e converter. Código de saída 0 = tudo certo.
O relatório é gravado em <pasta de dados>/selftest.log.
"""
from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path


def run() -> int:
    from .config import app_data_dir
    report = app_data_dir() / "selftest.log"
    lines = []

    def log(msg):
        lines.append(msg)
        report.write_text("\n".join(lines), "utf-8")

    import sys
    if not sys.platform.startswith("win"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import pymupdf
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from . import converters as conv
        from .document import PdfDocument, split_document, split_groups
        from .fonts import catalog, resolve_font
        from .tasks import run_task

        app = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp(prefix="vorticis_selftest_"))
        catalog.load()
        log(f"fontes do sistema: {len(catalog.fonts)}")

        files = []
        for n in range(3):
            d = pymupdf.open()
            for k in range(2):
                pg = d.new_page()
                pg.insert_text((72, 100), f"Documento {n} página {k}", fontsize=12)
                pg.insert_text((72, 112), "linha vizinha", fontsize=12)
                pg.draw_line((72, 130), (300, 130))
            f = tmp / f"doc{n}.pdf"
            d.save(f)
            files.append(str(f))
        log("PDFs de teste criados")

        pd = PdfDocument(files[0])
        page = pd.doc[0]
        span = next(s | {"dir": l["dir"]} for b in page.get_text("dict")["blocks"]
                    for l in b.get("lines", []) for s in l["spans"] if "Documento" in s["text"])
        font = resolve_font(pd.doc, page, span["font"], span["flags"], "Editado ç")
        pd.replace_text(0, span, "Editado ç", font, span["size"], (0, 0, 0))
        texts = pd.doc[0].get_text()
        assert "linha vizinha" in texts and "Editado" in texts, texts
        assert len(pd.doc[0].get_drawings()) == 1, "linha removida"
        log(f"edição de texto OK (fonte: {font.label} / {font.source})")

        # união pela tarefa em segundo plano (resultado volta na thread da interface)
        from .document import merge_files
        out = str(tmp / "unido.pdf")
        result = {}
        main_thread = app.thread()

        def done(info):
            from PySide6.QtCore import QThread
            result["info"] = info
            result["main"] = QThread.currentThread() is main_thread
            app.quit()

        run_task(None, "Unindo...", merge_files, files, out, on_done=done,
                 on_error=lambda m: (result.setdefault("err", m), app.quit()))
        QTimer.singleShot(60000, app.quit)
        app.exec()
        assert "err" not in result, result.get("err")
        assert result.get("main"), "resultado fora da thread principal"
        assert pymupdf.open(out).page_count == 6
        log("união em segundo plano OK (6 páginas)")

        parts = split_document(pymupdf.open(out), split_groups("every", 6, "2"), str(tmp / "sep"), "unido")
        assert len(parts) == 3
        log("separação OK")

        for fmt in ("docx", "xlsx", "png", "txt"):
            produced = conv.from_pdf(out, fmt, str(tmp / ("saida" + conv.FROM_PDF[fmt][1])))
            assert produced and all(os.path.getsize(p) > 0 for p in produced)
            log(f"conversão PDF -> {fmt} OK")
        conv.to_pdf(str(tmp / "saida.txt"), str(tmp / "de_txt.pdf"))
        log("conversão TXT -> PDF OK")
        # tradução da interface (pt-BR)
        from PySide6.QtWidgets import QDialogButtonBox
        from . import i18n
        i18n.install(app)
        box = QDialogButtonBox(QDialogButtonBox.Cancel)
        texts = [b.text() for b in box.buttons()]
        assert "Cancelar" in texts, texts
        log("interface em português OK")

        # OCR de página digitalizada (sem internet)
        from . import ocr
        srcd = pymupdf.open()
        pg = srcd.new_page()
        pg.insert_text((72, 100), "Relatório digitalizado de teste", fontsize=18)
        scan = pymupdf.open()
        sp = scan.new_page()
        sp.insert_image(sp.rect, pixmap=pg.get_pixmap(dpi=200))
        res = ocr.make_searchable(scan, [0], ["por"])
        assert res["paginas_ocr"] == [1] and scan[0].search_for("digitalizado"), res
        log(f"OCR OK ({res['palavras']} palavras; idiomas: {', '.join(ocr.available_langs())})")

        # assinatura digital com certificado A1 de teste + verificação
        import datetime as dt
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
        from . import signature as sig
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE VORTICIS:12345678901")])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(7).not_valid_before(now - dt.timedelta(days=1))
                .not_valid_after(now + dt.timedelta(days=30)).sign(key, hashes.SHA256()))
        pfx = tmp / "teste.pfx"
        pfx.write_bytes(pkcs12.serialize_key_and_certificates(
            b"t", key, cert, None, serialization.BestAvailableEncryption(b"1234")))
        signed = str(tmp / "assinado.pdf")
        page0 = pymupdf.open(out)[0]
        sig.sign_pdf(out, signed, a1_path=str(pfx), a1_password="1234", page_index=0,
                     rect=(72, 600, 300, 680), mediabox=tuple(page0.mediabox), reason="Teste")
        ver = sig.verify_pdf(signed)
        assert ver and ver[0]["integra"] and ver[0]["valida"] and ver[0]["cpf"] == "123.456.789-01", ver
        log("assinatura digital e verificação OK")
        log("RESULTADO: SUCESSO")
        return 0
    except Exception:
        log("RESULTADO: FALHA\n" + traceback.format_exc())
        return 1

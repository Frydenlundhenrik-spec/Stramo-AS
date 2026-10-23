"""Stramo sheet frame; embeds the original vector drawing without scaling it."""
import io
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ContentStream, FloatObject
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from branding import LOGO_PATH, logo_finnes, logo_sideforhold
from export_pdf import _registrer_font, draw_pdf_footer


def drawing_pdf(data, title="Tegninger"):
    font, bold = _registrer_font()
    writer = PdfWriter()
    source = PdfReader(io.BytesIO(data))
    for number, page in enumerate(source.pages, 1):
        # Change only black drawing ink, keeping all coordinates and labels intact.
        content=ContentStream(page.get_contents(),source)
        for i,(operands,operator) in enumerate(content.operations):
            if operator in (b'g',b'G',b'rg',b'RG') and all(float(v)==0 for v in operands):
                content.operations[i]=([FloatObject(v/255) for v in (7,56,76)],b'RG' if operator in (b'G',b'RG') else b'rg')
        page.replace_contents(content)
        width, height = float(page.mediabox.width)+48, float(page.mediabox.height)+108
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(width, height))
        c.setFillColor(HexColor("#07384c"))
        size = min(17, (width-155)/max(stringWidth(title,bold,17),1)*17)
        c.setFont(bold,size)
        c.drawString(24,height-34,title)
        if logo_finnes():
            c.drawImage(str(LOGO_PATH),width-101,height-48,width=77,height=77/logo_sideforhold(),mask="auto")
        c.setStrokeColor(HexColor("#d6e0e5"));c.setLineWidth(.5)
        c.line(24,height-60,width-24,height-60)
        c.setFillColor(HexColor("#07384c"));c.rect(24,14,width-48,26,fill=1,stroke=0)
        c.setFillColor(HexColor("#d5e600"));c.rect(24,14,3,26,fill=1,stroke=0)
        draw_pdf_footer(c, number, width, left=36, right=36, y=24,
                        total_pages=len(source.pages), text_color=HexColor("#ffffff"))
        c.save()
        framed=PdfReader(buffer).pages[0]
        framed.merge_transformed_page(page,Transformation().translate(24,48))
        writer.add_page(framed)
    writer.add_metadata({"/Title":title,"/Author":"Stramo"})
    result=io.BytesIO();writer.write(result)
    return result.getvalue()

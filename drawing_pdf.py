"""Fit each vector drawing to a printable A4 sheet, preserving its proportions."""
import io
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ContentStream, FloatObject
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
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
        box = page.cropbox
        sw, sh = float(box.width), float(box.height)
        margin, top, bottom = 10*mm, 62, 57
        def fit(sheet):
            return min((sheet[0]-2*margin)/sw, (sheet[1]-top-bottom)/sh)
        width, height = max((A4, landscape(A4)), key=fit)
        scale = fit((width,height))
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(width, height))
        c.setFillColor(HexColor("#07384c"))
        size = min(17, (width-155)/max(stringWidth(title,bold,17),1)*17)
        c.setFont(bold,size)
        c.drawString(margin,height-40,title)
        if logo_finnes():
            ratio = logo_sideforhold()
            logo_w = min(68, (55-margin)*ratio)
            c.drawImage(str(LOGO_PATH),width-margin-logo_w,height-55,width=logo_w,height=logo_w/ratio,mask="auto")
        c.setStrokeColor(HexColor("#d6e0e5"));c.setLineWidth(.5)
        c.line(margin,height-60,width-margin,height-60)
        c.setFillColor(HexColor("#07384c"));c.rect(margin,margin,width-2*margin,21,fill=1,stroke=0)
        c.setFillColor(HexColor("#d5e600"));c.rect(margin,margin,3,21,fill=1,stroke=0)
        draw_pdf_footer(c, number, width, left=margin+10, right=margin+10, y=margin+7,
                        total_pages=len(source.pages), text_color=HexColor("#ffffff"))
        c.save()
        framed=PdfReader(buffer).pages[0]
        dx = (width - scale*sw)/2
        dy = bottom + (height-top-bottom-scale*sh)/2
        framed.merge_transformed_page(page,Transformation().translate(-float(box.left),-float(box.bottom))
                                      .scale(scale).translate(dx,dy))
        writer.add_page(framed)
    writer.add_metadata({"/Title":title,"/Author":"Stramo"})
    result=io.BytesIO();writer.write(result)
    return result.getvalue()

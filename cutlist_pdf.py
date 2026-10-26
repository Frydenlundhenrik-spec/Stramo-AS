"""Printable cutting lists generated from the same quantities as the app."""
import io
from xml.sax.saxutils import escape
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, Table, TableStyle, PageBreak, Image
from branding import LOGO_PATH, logo_finnes, logo_sideforhold
from export_pdf import _registrer_font, draw_pdf_footer
from project_file import world_input
from kalkulasjon import beregn_prosjekt
from database import PANEL_DB
from construction import fixing_screw_count
from finishing import plywood_cuts, trim_order, board_count
from purchase_summary import with_totals, grouped_panels, grouped_cuts


MATERIAL_COLUMNS = {
    "Elementer": ["Produkt","Høyde_mm","Bredde_mm","Tykkelse_mm","Stk","Areal_m2"],
    "Beslag": ["Produkt","Stk"],
    "Dører": ["Produkt","Stk"],
    "Tilbehør": ["Produkt","Stk"],
}


def project_materials(rooms):
    """Purchase quantities, grouped by product and actual delivery dimensions."""
    rows=[]
    for _,p in grouped_panels(rooms).iterrows():
        rows.append(dict(Gruppe="Elementer",Produkt=p.Panel,Høyde_mm=p.Leveringslengde_mm,
            Bredde_mm=p.Bredde_mm,Tykkelse_mm=p.Tykkelse_mm,Stk=p.Bestill_hele_elementer,
            Areal_m2=p.Bestill_m2,Vekt_kg=p.Bestill_vekt_kg))
    for room in rooms:
        inp=world_input(room);form=room["form"]
        result=beregn_prosjekt(inp,pris_override=room.get("prices",{}))
        for _,r in result["df_mat"].iterrows():
            if r.Post.startswith(("Vegg ","Tak (panel)","Gulv", "Skruer", "Innv. hjørnebeslag", "Utv. hjørnebeslag")):continue
            group="Beslag" if r.Post.startswith("U-kanal") else ("Dører" if r.Post=="Dør" else "Tilbehør")
            product=r.Type.removesuffix(" – PRIS MANGLER")
            rows.append(dict(Gruppe=group,Produkt=product,Stk=None if product=="Varmekabel pr. m" else r.Mengde,
                Løpemeter=r.Mengde*2.5 if r.Post.startswith("U-kanal") else (r.Mengde if r.Type=="Varmekabel pr. m" else None)))
        bb=result["beslag"]
        screws=fixing_screw_count(inp.pts,inp.hoyde_m,inp.rom_type,PANEL_DB[inp.panel_key]["t"]/1000,inp.excluded_walls)
        rows.append(dict(Gruppe="Tilbehør",Produkt="22 mm hvite skruer",Stk=screws))
        for label,key in (("Innvendig 50×50 mm","kapp_inn"),("Utvendig 50×150 mm","kapp_ut")):
            net=sum(2500-r["Rest_mm"] for r in bb[key])/1000
            qty=trim_order(net)
            rows.append(dict(Gruppe="Beslag",Produkt=label+" · 0,6 mm stål · RAL 9010 · lengde 2500 mm",Stk=qty,Løpemeter=qty*2.5))
        if inp.rom_type=="Fryserom":
            w,l=form.get("plywood_width_mm",1500),form.get("plywood_length_mm",3000)
            qty=board_count(plywood_cuts(inp.pts,w,l))
            rows.append(dict(Gruppe="Tilbehør",Produkt=f"Gulvplate 12 mm – {w} × {l} mm",Stk=qty,Areal_m2=qty*w*l/1e6))
        quantities=form.get("accessory_quantities",{})
        for key,label,column in (("fugemasse","Fugemasse","Stk"),("skum","Skum","Stk"),
                                 ("pakninger","Pakninger","Løpemeter"),("alarm","Alarm","Stk")):
            rows.append(dict(Gruppe="Tilbehør",Produkt=label,**{column:quantities.get(key)}))
    columns=["Gruppe","Produkt","Høyde_mm","Bredde_mm","Tykkelse_mm","Stk","Areal_m2","Vekt_kg","Løpemeter"]
    frame=pd.DataFrame(rows).reindex(columns=columns)
    # A missing manual quantity in any room must not become a seemingly complete project total.
    return frame.groupby(columns[:5],dropna=False,sort=False,as_index=False)[columns[5:]].agg(
        lambda values:values.sum(min_count=len(values)))


def material_tables(frame):
    for group,columns in MATERIAL_COLUMNS.items():
        part=frame[frame.Gruppe==group][columns]
        if not part.empty:
            if group=="Elementer":
                total={"Produkt":"SUM"}
                total.update({c:part[c].sum(min_count=1) for c in ("Stk","Areal_m2")})
                part=pd.concat([part,pd.DataFrame([total])],ignore_index=True)
            yield group,part


def cutting_pdf(rooms, kind="alle"):
    font,bold = _registrer_font()
    out = io.BytesIO()
    page_w,page_h = landscape(A4)
    doc = SimpleDocTemplate(out,pagesize=(page_w,page_h),leftMargin=28,rightMargin=28,topMargin=32,bottomMargin=32)
    ink=colors.HexColor("#07384c")
    muted=colors.HexColor("#526b78")
    pale=colors.HexColor("#f3f7f9")
    rule=colors.HexColor("#d6e0e5")
    lime=colors.HexColor("#d5e600")
    normal = ParagraphStyle("cell",fontName=font,fontSize=8,leading=11,textColor=ink)
    head = ParagraphStyle("heading",fontName=bold,fontSize=14,leading=19,spaceAfter=8,keepWithNext=True,textColor=ink)
    note = ParagraphStyle("note",fontName=font,fontSize=8,leading=12,spaceAfter=10,textColor=muted)
    metadata = ParagraphStyle("metadata",parent=note,leading=11,spaceAfter=6)
    room_label="PROSJEKT "+", ".join(dict.fromkeys(r["input"].get("pnr", "") for r in rooms))+"  |  "+", ".join(r["input"]["navn"] for r in rooms)
    story = []

    def para(text,style=normal):
        return Paragraph(escape(str(text)).replace("\n","<br/>"),style)

    def table(frame,category=None):
        if frame.empty:
            story.append(para("Ingen poster.",note));return
        def value(v):
            if pd.isna(v):return "–"
            if isinstance(v,(float,int)):
                return f"{v:,.3f}".rstrip("0").rstrip(".").replace(","," ").replace(".",",")
            return str(v)
        labels={"Produkt":"Produkt" if category=="Elementer" else category or "Produkt", "Panel":"Panel", "Høyde_mm":"Høyde / lengde\nmm",
            "Leveringslengde_mm":"Leveringslengde\nmm", "Bredde_mm":"Bredde\nmm", "Tykkelse_mm":"Tykkelse\nmm",
            "Stk":"Antall (stk)", "Antall_stk":"Antall (stk)", "Deler_stk":"Deler\nstk",
            "Areal_m2":"Areal\nm²", "Vekt_kg":"Vekt\nkg", "Løpemeter":"Lengde\n"+("m" if category=="Tilbehør" else "LM"),
            "Bestill_hele_elementer":"Bestilling\nstk", "Bestill_hele_plater":"Hele plater\nstk",
            "Bestill_lm":"Bestilling\nlm", "Bestill_m2":"Bestilling\nm²", "Bestill_vekt_kg":"Bestilling\nkg",
            "Vektgrunnlag":"Vektgrunnlag", "Antall_stenger":"Antall stenger\nstk", "Kapp_pr_stang":"Kapp per 2500 mm stang",
            "Rest_pr_stang_mm":"Rest per stang\nmm", "Netto_lm":"Netto\nlm", "Kapp_prosent":"Kapp\n%",
            "Lm_med_kapp":"Inkl. kapp\nlm", "Bestill_stk":"Bestilling\nstk", "Netto_m2":"Netto\nm²"}
        text_weights={"Produkt":2.7 if category=="Elementer" else 4.8,"Panel":1.6,"Rom":2.4,"Profil":2.2,"Vektgrunnlag":1.9,"Kapp_pr_stang":3.8,"Merknad":2.2}
        text_columns=set(text_weights)|{"Plate","ID","Del"}
        weights=[text_weights.get(c,1) for c in frame.columns]
        widths=[(page_w-56)*w/sum(weights) for w in weights]
        if category in ("Beslag", "Dører", "Tilbehør"):
            widths=[(page_w-56)*.85, (page_w-56)*.15]
        header_style=ParagraphStyle("table_header",parent=normal,fontName=bold,textColor=colors.white,fontSize=7,leading=10)
        total_style=ParagraphStyle("table_total",parent=normal,fontName=bold,textColor=colors.white)
        def cell(text,col,style):
            aligned=ParagraphStyle("aligned",parent=style,alignment=0 if col in text_columns else 2)
            return para(text,aligned)
        cells=[[cell(labels.get(c,str(c).replace("_"," ")),c,header_style) for c in frame.columns]]
        totals=[]
        for i,row in enumerate(frame.itertuples(index=False,name=None),1):
            is_total=any(str(v).startswith("SUM") for v in row)
            if is_total:totals.append(i)
            cells.append([cell(value(v),c,total_style if is_total else normal) for c,v in zip(frame.columns,row)])
        t = LongTable(cells,colWidths=widths,repeatRows=1,hAlign="LEFT")
        commands = [("BACKGROUND",(0,0),(-1,0),ink),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,pale]),
                    ("LINEBELOW",(0,0),(-1,0),2,lime),("LINEBELOW",(0,1),(-1,-1),.3,rule),
                    ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
                    ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
                    ("TOPPADDING",(0,0),(-1,0),6),("BOTTOMPADDING",(0,0),(-1,0),6)]
        for i in totals:
            commands.extend([("BACKGROUND",(0,i),(-1,i),ink),("LINEBEFORE",(0,i),(0,i),3,lime),
                ("NOSPLIT",(0,max(1,i-1)),(-1,i))])
        t.setStyle(TableStyle(commands));t.spaceAfter=8;story.append(t)

    def section(title):
        if story:story.append(PageBreak())
        if logo_finnes():
            logo=Image(str(LOGO_PATH),width=64,height=64/logo_sideforhold(),hAlign="RIGHT")
            header=Table([[para(title,head),logo]],colWidths=[page_w-132,76])
            header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
            story.append(header)
        else:
            story.append(para(title,head))
        story.append(para(room_label,metadata))

    if kind=="materialer":
        accessory_page=False
        for title,frame in material_tables(project_materials(rooms)):
            if title=="Elementer":
                section("Elementer")
            elif not accessory_page:
                section("Materialliste")
                accessory_page=True
            table(frame,title)
    if kind in ("alle","elementer") and rooms:
        section("Elementliste")
        story.append(para("Ferdige deler med samme høyde, bredde og tykkelse summeres på én linje. Paneltyper holdes adskilt. Vekt er estimert når leverandørvekt ikke er oppgitt.",note))
        table(with_totals(grouped_cuts(rooms),["Antall_stk","Areal_m2","Vekt_kg"],"Panel"))
        section("Elementbestilling")
        story.append(para("Lengder leveres på mål. Antallet følger beregnet behov uten prosentvis kapptillegg. Én råplate per element; avkapp deles ikke mellom elementer. Vekt merket ESTIMAT gjelder bare paneler, uten dører, beslag, gulvplater og emballasje.",note))
        table(with_totals(grouped_panels(rooms).drop(columns="Bestill_lm"),["Bestill_hele_elementer","Bestill_m2","Bestill_vekt_kg"],"Panel"))
    if kind in ("alle","beslag","beslagprofiler"):
        from beslag_profiles import profile_rows, profile_cards
        section("Beslagsliste")
        profiles=profile_rows(project_materials(rooms))
        card_head=ParagraphStyle("profilehead",parent=head,fontSize=11,leading=14,spaceAfter=6)
        card_text=ParagraphStyle("profiletext",parent=note,fontSize=9,leading=14)
        story.extend(profile_cards(profiles,card_text,card_head,page_w-56))
        total_lm=f'{sum(p["lm"] for p in profiles):g}'.replace('.', ',')
        total_style=ParagraphStyle("profile_total",parent=note,fontName=bold,textColor=colors.white,fontSize=11,leading=15,spaceAfter=0)
        total=Table([[para("TOTAL BESTILLING",total_style),para(f'{sum(p["qty"] for p in profiles)} stk  /  {total_lm} LM',total_style)]],colWidths=[270,page_w-326])
        total.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#07384c")),
            ("LINEBEFORE",(0,0),(0,0),3,colors.HexColor("#d5e600")),
            ("LEFTPADDING",(0,0),(-1,-1),16),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        story.append(total)
    if kind in ("alle","finer"):
        sums=[]
        for room in rooms:
            inp=world_input(room)
            if inp.rom_type!="Fryserom":continue
            form=room["form"];w,l=form.get("plywood_width_mm",1500),form.get("plywood_length_mm",3000)
            waste=0;cuts=plywood_cuts(inp.pts,w,l)
            section(f"Gulvplatekappliste – {inp.navn}")
            story.append(para(f"Gulvplate 12 mm, råplate {w} × {l} mm. Monteres innenfor veggene. Råplatenummer viser hvilke deler som kappes av samme plate. Avkapp over 200 mm i begge retninger vurderes for gjenbruk, med 3 mm sagspor.",note))
            table(pd.DataFrame([{k:v for k,v in r.items() if k in ("Plate", "Bredde_mm", "Lengde_mm", "Areal_m2", "Råplate")} for r in cuts]))
            qty=board_count(cuts)
            sums.append(dict(Rom=inp.navn,Deler_stk=len(cuts),Netto_m2=sum(r["Areal_m2"] for r in cuts),
                Kapp_prosent=waste,Bestill_hele_plater=qty,Bestill_m2=qty*w*l/1e6))
        if sums:
            if len(sums)==1:
                story.append(para("Gulvplater – totalsummer",head))
            else:
                section("Gulvplater – totalsummer")
            table(with_totals(pd.DataFrame(sums),["Deler_stk","Netto_m2","Bestill_hele_plater","Bestill_m2"],"Rom"))
    if not story:story.append(para("Ingen kapplister i prosjektet."))

    def footer(canvas,document):
        canvas.setStrokeColor(rule)
        canvas.setLineWidth(.5)
        canvas.line(28,28,page_w-28,28)
        draw_pdf_footer(canvas,document.page,page_w,left=28,right=28,y=16,text_color=muted)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def pdf_downloads(rooms):
    import streamlit as st
    if not rooms:return
    st.subheader("Kapplister som PDF")
    from beslag_profiles import profile_rows, profile_png
    with st.expander("Detaljert beslagsliste med profiltegninger"):
        profiles=profile_rows(project_materials(rooms))
        if logo_finnes():st.image(str(LOGO_PATH),width=110)
        st.caption("Valgte rom: "+", ".join(r["input"]["navn"] for r in rooms))
        for r in profiles:
            left,right=st.columns([1,1])
            left.image(profile_png(r["kind"],r["width"]))
            right.markdown(f'**{r["name"]}**\n\n**{r["qty"]} stk × 2500 mm = {r["lm"]:g} LM**\n\n0,6 mm stål · RAL 9010')
        st.markdown(f'**TOTAL BESTILLING: {sum(r["qty"] for r in profiles)} stk · {sum(r["lm"] for r in profiles):g} LM**')
        st.download_button("Detaljert beslagsliste – PDF",cutting_pdf(rooms,"beslagprofiler"),"beslagsliste-profiler.pdf","application/pdf",key="cutpdf_profiles")
    for kind,label in (("alle","Alle kapplister samlet"),("elementer","Elementkapplister"),("finer","Gulvplatekapplister")):
        if kind=="finer" and not any(r["input"]["rom_type"]=="Fryserom" for r in rooms):continue
        st.download_button(label+" – PDF",cutting_pdf(rooms,kind),f"kapplister-{kind}.pdf","application/pdf",key=f"cutpdf_{kind}")


def material_downloads(rooms, all_rooms=True):
    import streamlit as st
    if not rooms:return
    scope = "hele prosjektet" if all_rooms else "valgt rom"
    st.subheader("Elementliste")
    frame=project_materials(rooms)
    for title,part in material_tables(frame):
        display=part.rename(columns={"Produkt":"Produkt" if title=="Elementer" else title,"Stk":"Antall (stk)","Høyde_mm":"Høyde / lengde (mm)",
            "Bredde_mm":"Bredde (mm)","Tykkelse_mm":"Tykkelse (mm)","Areal_m2":"Areal (m²)",
            "Løpemeter":"Lengde (m)" if title=="Tilbehør" else "Lengde (LM)"})
        st.dataframe(display,hide_index=True)
    st.download_button("Materialliste " + scope + " – PDF",cutting_pdf(rooms,"materialer"),"materialliste-prosjekt.pdf","application/pdf",key="project_material_pdf")
    st.download_button("Materialliste " + scope + " – CSV",frame.to_csv(index=False).encode("utf-8-sig"),"materialliste-prosjekt.csv","text/csv",key="project_material_csv")

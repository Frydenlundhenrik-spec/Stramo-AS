"""Assemble the supplied, unchanged supplier PDFs into Stramo's reusable FDV pack."""
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import hashlib
import shutil
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from pypdf import PdfReader, PdfWriter
from branding import LOGO_PATH, logo_sideforhold
from export_pdf import _registrer_font, draw_pdf_footer

ROOT=Path(__file__).parent
DEFAULT_OUTPUT=ROOT/'output'/'Stramo-standard-FDV-2026-10-23'
DEFAULT_SOURCES=ROOT/'assets'/'fdv'
FONT,BOLD=_registrer_font()
BLUE=colors.HexColor('#07384c')
MUTED=colors.HexColor('#526b78')
PALE=colors.HexColor('#f3f7f9')
LIME=colors.HexColor('#d5e600')
STYLES={
    'title':ParagraphStyle('title',fontName=BOLD,fontSize=25,leading=31,textColor=BLUE,spaceAfter=18),
    'heading':ParagraphStyle('heading',fontName=BOLD,fontSize=17,leading=22,textColor=BLUE,spaceAfter=14),
    'sub':ParagraphStyle('sub',fontName=BOLD,fontSize=11,leading=15,textColor=BLUE,spaceBefore=12,spaceAfter=7),
    'body':ParagraphStyle('body',fontName=FONT,fontSize=10,leading=15,spaceAfter=9,textColor=BLUE),
    'cell':ParagraphStyle('cell',fontName=FONT,fontSize=9,leading=12,textColor=BLUE),
    'tablehead':ParagraphStyle('tablehead',fontName=BOLD,fontSize=9,leading=12,textColor=colors.white),
}
def p(text,style='body'):
    return Paragraph(escape(text).replace('\n','<br/>'),STYLES[style])
def table(rows,widths):
    t=Table([[p(str(v),'tablehead' if i==0 else 'cell') for v in row] for i,row in enumerate(rows)],colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,0),(-1,0),2,LIME),
        ('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#d6e0e5')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    return t
def chrome(c,doc,first_page=1):
    c.saveState()
    c.drawImage(str(LOGO_PATH),A4[0]-137,A4[1]-62,width=89,height=89/logo_sideforhold(),mask='auto')
    c.setFont(FONT,8);c.setFillColor(MUTED)
    c.drawString(44,A4[1]-46,'STRAMO / FORVALTNING, DRIFT OG VEDLIKEHOLD')
    c.setFillColor(BLUE);c.rect(44,A4[1]-76,A4[0]-88,3,fill=1,stroke=0)
    c.setFillColor(LIME);c.rect(44,A4[1]-76,52,3,fill=1,stroke=0)
    c.setFillColor(BLUE);c.rect(44,15,A4[0]-88,24,fill=1,stroke=0)
    c.setFillColor(LIME);c.rect(44,15,3,24,fill=1,stroke=0)
    draw_pdf_footer(c,first_page+doc.page-1,A4[0],left=54,right=54,y=23,text_color=colors.white)
    c.restoreState()
def pdf(path,story,first_page=1):
    def page_chrome(c,doc):
        chrome(c,doc,first_page)
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=88,bottomMargin=50,
        title='Stramo standard FDV - paneler og beslag',author='Stramo',
        subject='Revisjon 09 - 26.10.2026').build(story,onFirstPage=page_chrome,onLaterPages=page_chrome)

sources=[
 ('01_Paneler','01_Produktdatablad.pdf','Produktdatablad - PIR STANDARD','BALEX-pu-w-st-wall-sandwich-panel-polyurethane-core-2026-10-22.pdf'),
 ('01_Paneler','02_Ytelseserklaering.pdf','Ytelseserklæring - PU-PIR-W-ST','Declaration of Performance_ PU-PIR-W-ST2.pdf'),
 ('01_Paneler','03_Hygienesertifikat.pdf','Hygienesertifikat - PIR-paneler','PU PIR Hygiene Certificate_ polyurethane core sandwich panel (EN).pdf'),
 ('01_Paneler','04_EPD.pdf','Miljødeklarasjon - PIR-paneler','Environmental Product Declaration (EPD) - Panels with PIR insulation layer.pdf'),
 ('01_Paneler','05_Teknisk_katalog.pdf','Teknisk katalog - PIR-paneler','Technical Catalogue_ PIR sandwich panels.pdf'),
 ('01_Paneler','06_Monteringsanvisning.pdf','Monteringsanvisning - sandwichpaneler','Sandwich panel assembly instruction (EN).pdf'),
 ('02_Beslag','01_Beslagskatalog.pdf','Teknisk katalog - beslag','Balex Katalog Techniczny Obróbki Blacharskie EN 2025.pdf'),
]
def build_standard_fdv(output_dir=None, source_dir=None, *, project_name="", project_number="", room_names=()):
    """Build the standard pack from unmodified supplier PDFs; return its PDF path.

    source_dir can contain the numbered bundled folders or the original PDF
    filenames. No user-specific paths or network access are required.
    """
    OUT=Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT
    source_root=Path(source_dir) if source_dir is not None else DEFAULT_SOURCES
    source_paths={}
    for folder,name,title,original in sources:
        path=source_root/folder/name
        if not path.is_file():
            path=source_root/original
        if not path.is_file():
            raise FileNotFoundError(f"FDV-vedlegg mangler: {original}. Legg dokumentet i {source_root}.")
        source_paths[(folder,name)]=path
    OUT.mkdir(parents=True,exist_ok=True)
    room_names=tuple(str(name) for name in room_names)
    entries=[]
    next_page=6
    for folder,name,title,original in sources:
        src=source_paths[(folder,name)];dest=OUT/folder/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src,dest)
        pages=len(PdfReader(src).pages)
        entries.append(dict(title=title,path=dest,original=original,pages=pages,start=next_page,status='Vedlagt'))
        next_page+=pages

    pending=[
     ('03_Skruer','Skruer','22 mm hvite skruer',[
      'Produsent, produktnavn og artikkelnummer; diameter og lengde.',
      'Produktdatablad med materiale, overflate og korrosjonsbeskyttelse.',
      'Anvisning for innfesting, egnede underlag og kontroll/utskifting.'],
      'Prosjektert festeprinsipp: to skruerekker på hjørnebeslag og fryserommets gulvbeslag, med maks. 400 mm avstand langs hver rekke. Produktets egnethet og innfestingen bekreftes for leveransen.'),
     ('04_Fugemasse','Fugemasse','Produkt velges/bekreftes for leveransen',[
      'Produsent, produktnavn, artikkelnummer og valgt farge.',
      'Teknisk datablad og sikkerhetsdatablad der dette foreligger/kreves.',
      'Dokumentasjon på egnede underlag, temperaturgrenser, herding, rengjøring og utskifting.'],
      'Bekreft kompatibilitet med panelenes lakk, tetninger og planlagte rengjøringsmidler. Ikke angi fugemassen som godkjent for direkte matkontakt uten dokumentasjon.'),
     ('05_Fiberplater','Gulvplater','12 mm beskyttende gulvplate, 1500 × 3000 mm',[
      'Produsent, produktnavn, artikkelnummer, tykkelse og plateformat.',
      'Produktdatablad og monterings-/vedlikeholdsanvisning.',
      'Opplysninger om fukt- og temperaturegenskaper, eventuell overflatebehandling og belastning.'],
      'Platen legges innvendig som beskyttelse over fryseromsgulvet. Samlet gulvoppbygging, understøttelse og tillatt belastning må dokumenteres for prosjektet.'),
    ]
    pending_documents=[]
    for folder,title,product,needed,note in pending:
        dest=OUT/folder/'00_Dokumentasjon_kommer.pdf';dest.parent.mkdir(exist_ok=True)
        story=[p(title,'title'),p('DOKUMENTASJON ETTERSENDES','sub'),p('Reservert seksjon i standard FDV-pakke. Dette arket er en plassholder, ikke et produktdatablad.'),
            p('Planlagt produkt','sub'),p(product),p('Dokumenter som legges inn senere','sub')]
        story += [p(f'{i}. {text}') for i,text in enumerate(needed,1)]
        story += [p('Prosjekttilknytning','sub'),p(note),Spacer(1,12),table([
            ['Felt','Fylles ut når produktet er bekreftet'],['Produsent / produkt',''],['Dokumentnavn / revisjon',''],['Dato lagt til / ansvarlig',''],['Kontrollert mot leveranse','']],[177,330])]
        pending_documents.append((dest,story))
        entries.append(dict(title=title+' - dokumentasjon ettersendes',path=dest,original='',pages=1,start=next_page,status='Ettersendes'))
        next_page+=1

    def front_story():
        return [p('Standard FDV-pakke','title'),p('Paneler og beslag til kjøle- og fryserom','heading'),
         p('Dokumentgrunnlag: BALEX PIR STANDARD og teknisk dokumentasjon for beslag. Pakken inneholder originaldokumenter og en kort Stramo-oversikt for bruk og vedlikehold.'),
         p('Status ved utgivelse','sub'),p('Panel- og beslagsdokumentasjon er vedlagt. Egne seksjoner er reservert for skruer, fugemasse og 12 mm gulvplater. Disse produktdokumentene legges til senere.'),
         table([['Prosjektopplysninger','Fylles ut for aktuell leveranse'],['Prosjekt / adresse',project_name],['Prosjektnummer / rom',f'{project_number} / {chr(10).join(room_names)}'.strip(' /')],['Dokument / dato','Revisjon 09 / 26.10.2026'],['Byggherre / eier',''],['Leverandør / montør / kontakt',''],['Leveringsdato / overleveringsdato','']],[177,330]),
         p('Pakkens omfang','sub'),p('Dette er en standard delpakke for paneler, platebeslag og tilhørende festing, fuging og gulvbeskyttelse. Prosjektets tegninger og materialliste legges ved aktuell leveranse. Dører, trykkventiler, kjølemaskineri og elektro dokumenteres separat der de inngår.'),
         p('Bruk av pakken','sub'),p('Kontroller produktvalg og revisjoner mot faktisk leveranse. Leverandørens originalanvisninger gjelder. Denne standardpakken er ikke en godkjenning av en bestemt konstruksjon eller en fullstendig FDV for hele kjøleanlegget.'),PageBreak(),
         p('Dokumentoversikt','title'),p('Sidene nedenfor viser plasseringen i den samlede PDF-en. Originalvedleggene beholder sin egen sidenummerering. Bokmerker gir direkte tilgang til hver del.'),
         table([['Dokument','Status','PDF-side']]+[[e['title'],e['status'],f"{e['start']}-{e['start']+e['pages']-1}"] for e in entries],[340,87,80]),
         p('Redigering og supplering','sub'),p('De samme dokumentene ligger som enkeltfiler i nummererte mapper. Legg nye dokumenter i mappene for skruer, fugemasse og gulvplater, og oppdater dokumentregisteret. Den samlede PDF-en må bygges på nytt når dokumenter legges til.'),PageBreak(),
         p('Produkter og overflater','title'),
         p('Paneler','sub'),p('BALEX PIR STANDARD, produktkode PU-PIR-W-ST. Prosjektet kan benytte 80 mm panel i kjølerom og 100 mm panel i fryserom. Endelig tykkelse, bredde, lengde, ståltykkelse og profilering fremgår av prosjektets leveranseliste.'),
         p('Bekreftet overflatebelegg for panelene: PE25 polyesterlakk, 25 µm, RAL 9010. Beleggtypen og tykkelsen er oppgitt av oppdragsgiver 22.10.2026. Leverandørens originaldokumenter beskriver også andre produktalternativer; denne FDV-pakken gjelder det bekreftede PE25-belegget.'),
         p('Platebeslag','sub'),p('Prosjekterte profiler: innvendig vinkel 50 × 50 mm, utvendig vinkel 50 × 150 mm og U-kanal for 80 mm kjøleromspanel med 50 mm sider. Angitt utførelse: 0,6 mm stål, RAL 9010, 10 mm omknekk og 2500 mm lengde. Fryserommet har gulvbeslag i stedet for U-kanal.'),
         p('Bekreftet overflatebelegg for beslagene: PE25 polyesterlakk, 25 µm, RAL 9010, oppgitt av oppdragsgiver 22.10.2026. Beslagskatalogen dokumenterer ikke automatisk de prosjekttilpassede profilene ovenfor. Faktisk produsent og ståltype bekreftes mot leveransen; Stramos beslagstegninger vedlegges som geometrigrunnlag.'),
         p('Hygiene og miljø','sub'),p('Hygienesertifikatet omfatter PIR STANDARD i blant annet næringsmiddelbygg uten direkte kontakt med mat. EPD-en beskriver miljøegenskaper og erstatter ikke monterings- eller vedlikeholdsanvisninger.'),
         p('Gulv i fryserom','sub'),p('Planlagt løsning er panelgulv på 22 mm lekter, vegger oppå panelgulvet og 12 mm gulvplate, 1500 × 3000 mm, innenfor veggene. Ytelseserklæringen beskriver vegger og himlinger. Gulvets understøttelse og tillatte flate-/punktlaster må derfor dokumenteres særskilt for valgt oppbygging.'),PageBreak(),
         p('Renhold og vedlikehold','title'),
         p('Grunnlag','sub'),p('Oppsummeringen bygger på monteringsanvisningen side 12 og 35 samt teknisk panelkatalog side 34. De fullstendige leverandøranvisningene følger vedlagt.'),
         table([['Oppgave','Rutine'],
         ['Årlig ettersyn','Kontroller forbindelser mellom paneler og beslag, panelkanter, lakkskader, festemidler og tetninger. Dokumenter skader og utførte tiltak.'],
         ['Renhold','Følg virksomhetens renholdsplan og bruk midler som er forenlige med valgt lakk og tetninger. Leverandøren beskriver milde rengjøringsmidler for lett tilsmussing etter montasje. Dette fastsetter ikke et eget desinfeksjonsregime for rommet.'],
         ['Metallspon og urenheter','Fjern metallspon slik at de ikke korroderer og skader lakken. Monteringsanvisningen beskriver nylonbørste og egnet rengjøring. Unngå bensin/petroleumsprodukter som rengjøringsmiddel.'],
         ['Lakkskader','Utbedre skader med kompatibel reparasjonslakk etter leverandørens anvisning. Vurder større skader med leverandøren.'],
         ['Skruer og tetninger','Løse festemidler ettertrekkes eller skiftes etter produktets anvisning; korroderte festemidler skiftes. Skadde eller manglende tetninger utbedres. Produktspesifikke anvisninger ettersendes.'],
         ['Gulvplate','Kontroller synlige skader og fuktpåvirkning. Rengjøringsmiddel, fukttoleranse og vedlikeholdsintervall fastsettes når valgt plate er dokumentert.']],[115,392]),
         p('Skader og avvik','sub'),p('Registrer sted, dato, skade og tiltak. Kontakt ansvarlig leverandør ved lekkasje, fukt i panelkjerne, løse beslag eller skader som ikke kan utbedres etter anvisningene.'),PageBreak(),
         p('Leveransekontroll og logg','title'),
         table([['Kontrollpunkt','Notat / dokumentreferanse'],['Paneler: overflate','PE25 polyesterlakk, 25 µm, RAL 9010. Bekreftet 22.10.2026.'],['Beslag: overflate','PE25 polyesterlakk, 25 µm, RAL 9010. Produsent og ståltype kontrolleres mot leveransen.'],['Skruer: produkt og dokumenter','Ettersendes'],['Fugemasse: produkt og dokumenter','Ettersendes'],['12 mm gulvplate: produkt og dokumenter','Ettersendes'],['Gulvoppbygging og belastning','Bekreftes for prosjektet'],['Prosjekttegninger / materialliste','Vedlegges aktuell leveranse'],['Kontrollert av / dato / revisjon','']],[270,237]),
         p('Vedlikeholdslogg','sub'),table([['Dato / rom','Kontroll, avvik og tiltak','Utført av']]+[['','',''] for _ in range(5)],[90,317,100]),
         p('Dokumenthenvisninger','sub'),p('Produktdata: paneldatablad side 3-5. Overflater: teknisk panelkatalog side 15. Vedlikehold: monteringsanvisning side 12 og 35. Bruksområde: ytelseserklæring side 1 og hygienesertifikat. Beslag: teknisk beslagskatalog og prosjektets egne tegninger.')]
    front=OUT/'00_FDV_oversikt.pdf'
    pdf(front,front_story())
    front_pages=len(PdfReader(front).pages)
    if front_pages != 5:
        # Long project names/room selections may add front pages. Keep all
        # document-register offsets and bookmarks aligned with the real PDF.
        shift=front_pages-5
        for entry in entries:
            entry['start']+=shift
        next_page+=shift
        pdf(front,front_story())
        if len(PdfReader(front).pages) != front_pages:
            raise ValueError("FDV-oversikten fikk ustabil paginering. Forkort prosjekt-/romnavn.")
    for path,story in pending_documents:
        first_page=next(entry['start'] for entry in entries if entry['path']==path)
        pdf(path,story,first_page=first_page)
        assert len(PdfReader(path).pages)==1
    writer=PdfWriter();writer.append(front,outline_item='Stramo - oversikt og vedlikehold')
    for e in entries:writer.append(e['path'],outline_item=e['title'],import_outline=False)
    writer.add_metadata({'/Title':'Stramo standard FDV - paneler og beslag','/Author':'Stramo','/Subject':'Revisjon 09 - 26.10.2026. Felles FDV i app og leveranse. PE25 polyesterlakk, 25 µm, på paneler og beslag'})
    merged=OUT/'Stramo-standard-FDV.pdf'
    with merged.open('wb') as f:writer.write(f)
    assert len(PdfReader(merged).pages)==next_page-1
    with (OUT/'Dokumentregister.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['Dokument','Status','Fil','Originalfil','PDF_startside','Sider','SHA256'])
        for e in entries:w.writerow([e['title'],e['status'],str(e['path'].relative_to(OUT)),e['original'],e['start'],e['pages'],hashlib.sha256(e['path'].read_bytes()).hexdigest()])
    (OUT/'LES-MEG.txt').write_text('STRAMO STANDARD FDV - revisjon 09, 26.10.2026\n\nRevisjon 06: Forenklet bunntekst med faktisk sidetall, omknekk-begrep og gulvplater 1500 × 3000 × 12 mm.\nRevisjon 04: Samme FDV-pakke i app og leveranse, med prosjekt og valgte rom. Originalvedlegg beholdt.\nRevisjon 03: Oppdatert visuelt Stramo-oppsett.\nRevisjon 02: PE25 polyesterlakk, 25 µm, RAL 9010 er bekreftet for paneler og beslag.\nÅpne Stramo-standard-FDV.pdf for hele pakken med bokmerker.\n00_FDV_oversikt.pdf inneholder den korte oversikten.\nLeverandørdokumentene ligger uendret i mapper 01 og 02.\nMapper 03, 04 og 05 er reservert for skruer, fugemasse og 12 mm gulvplater.\nFyll inn prosjektopplysninger og kontroller produktene mot leveransen.\nLegg ved prosjektets aktuelle tegninger og materialliste.\nOppdater Dokumentregister.csv og bygg samlet PDF på nytt ved supplering.\nDette er standarddelen for paneler og beslag, ikke full FDV for kjølemaskineri, elektro eller dører.\n',encoding='utf-8')
    return merged


def lag_standard_fdv_pdf(prosjektnavn="", prosjektnummer="", romnavn=(), *, source_dir=None):
    """The app and delivery use this same PDF content, including all attachments."""
    with TemporaryDirectory(prefix="stramo-fdv-") as tmp:
        path=build_standard_fdv(tmp, source_dir, project_name=prosjektnavn,
                                project_number=prosjektnummer, room_names=romnavn)
        return path.read_bytes()


if __name__ == "__main__":
    merged=build_standard_fdv()
    print(f"Created {merged}: {len(PdfReader(merged).pages)} pages, {merged.stat().st_size} bytes")

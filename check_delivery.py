from pathlib import Path
import sys
import ifcopenshell
from pypdf import PdfReader
root=Path(sys.argv[1] if len(sys.argv)>1 else 'output/Tasty-Fredrikstad-tegningspakke')
for p in root.rglob('*.ifc'):
 m=ifcopenshell.open(str(p));assert len(m.by_type('IfcDoor'))==2
for name in ('01-Kjolerom','02-Fryserom'):
 p=root/name/'00-Alle-tegninger.pdf'
 source=[x for x in (root/name).glob('*.pdf') if x.name[:2] in ('01','02','03','04','05','06')]
 assert len(PdfReader(p).pages)==sum(len(PdfReader(x).pages) for x in source)
text=PdfReader(root/'01-Kjolerom'/'04-Vegg-V6.pdf').pages[0].extract_text()
assert 'V34' not in text
assert 'V26' in text,text
assert not (root/'01-Kjolerom'/'04-Vegg-V4.pdf').exists()
assert not (root/'01-Kjolerom'/'04-Vegg-V5.pdf').exists()
assert len(PdfReader(root/'03-Sammenstilling'/'00-Alle-prosjekttegninger.pdf').pages)==2+sum(len(PdfReader(root/n/'00-Alle-tegninger.pdf').pages) for n in ('01-Kjolerom','02-Fryserom'))
production='\n'.join(p.extract_text() for p in PdfReader(root/'02-Fryserom'/'05-Produksjonstegninger.pdf').pages)
assert '4110' in production and '3910' not in production
print('PASS: merged books match source pages; freezer production 4110 mm; two doors per IFC; shared-wall exclusions')

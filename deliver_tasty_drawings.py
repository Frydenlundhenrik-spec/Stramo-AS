from pathlib import Path
from copy import deepcopy
import re,json,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from pypdf import PdfReader,PdfWriter
from project_file import decode_project,world_input
from project_ui import assembly_plan
from kalkulasjon import beregn_prosjekt
from montasje import *
from ifc_export import gen_ifc
from cutlist_pdf import cutting_pdf
from transport import packages,pack_floor,load_figure,transport_manifest
import plotly.graph_objects as go

root=Path(sys.argv[1] if len(sys.argv)>1 else 'output/Tasty-Fredrikstad-tegningspakke');root.mkdir(parents=True,exist_ok=True)
project=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes());rooms=project['rooms']
manifest=[]
def savefig(fig,path,title):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(figur_som_pdf(fig,title));plt.close(fig)
    manifest.append((str(path.relative_to(root)),title))
def merge(paths,out):
    w=PdfWriter()
    for p in paths:w.append(str(p),outline_item=p.stem)
    w.write(str(out));w.close()
def static3d(plot,title):
    fig=plt.figure(figsize=(14,9));ax=fig.add_subplot(111,projection='3d',computed_zorder=False);allpoints=[]
    for t in plot.data:
        if t.type=='scatter3d' and t.x is not None:
            color=t.line.color or '#526b78'
            if not isinstance(color,str) or color.startswith('rgb'):color='#526b78'
            ax.plot(np.asarray(t.x,dtype=float),np.asarray(t.y,dtype=float),np.asarray(t.z,dtype=float),color=color,
                    linewidth=1.1 if t.name=='Dørkarm' else .65,alpha=t.opacity if t.opacity is not None else .65,zorder=3)
            continue
        if t.type!='mesh3d' or t.x is None:continue
        v=np.array([t.x,t.y,t.z],dtype=float).T
        if not len(v):continue
        allpoints.extend(v)
        if t.i is not None:
            tris=np.column_stack([t.i,t.j,t.k]).astype(int)
            color=t.color or '#b4cbd8'
            if not isinstance(color,str) or color.startswith('rgb'):color='#b4cbd8'
            ax.add_collection3d(Poly3DCollection(v[tris],facecolor=color,edgecolor='none',linewidth=0,
                alpha=t.opacity if t.opacity is not None else .6,zorder=2 if (t.name or '').startswith('Dør') else 1))
    v=np.array(allpoints);lo=v.min(axis=0);hi=v.max(axis=0)
    ax.set_xlim(lo[0]-.2,hi[0]+.2);ax.set_ylim(lo[1]-.2,hi[1]+.2);ax.set_zlim(0,hi[2]+.2)
    ax.set_box_aspect(np.maximum(hi-lo,.1));ax.set_proj_type('ortho');ax.view_init(24,-65)
    ax.set_xlabel('X (m)');ax.set_ylabel('Y (m)');ax.set_zlabel('Z (m)');ax.set_title(title)
    return fig

def open_model(inp):
    return tegn_3d_modell(inp,apninger=inp.apninger)

allroompdf=[];combined=go.Figure()
for ri,room in enumerate(rooms):
    name='01-Kjolerom' if ri==0 else '02-Fryserom';folder=root/name;folder.mkdir(exist_ok=True)
    local=deepcopy(room);local['position_mm']=[0,0]
    inp=world_input(local);result=beregn_prosjekt(inp)
    roompdf=[]
    def add(fig,filename,title):
        path=folder/filename;savefig(fig,path,title);roompdf.append(path)
    if inp.excluded_walls:
        fig=assembly_plan([local])
    else:fig=tegn_plantegning(inp,result,apninger=inp.apninger)
    add(fig,'01-Plantegning.pdf','Plantegning')
    add(tegn_taktegning(inp,result),'02-Tak-og-gulv.pdf','Taktegning / fryseromsgulv')
    if inp.rom_type=='Fryserom':
        from finishing import plywood_plan
        add(plywood_plan(inp.pts,room['form'].get('plywood_width_mm',1500),room['form'].get('plywood_length_mm',3000),PANEL_DB[inp.panel_key]['t']/1000),
            '02-Gulvplateplan.pdf','Gulvplateplan')
    for wi in range(len(inp.pts)):
        if wi in inp.excluded_walls:continue
        add(tegn_snitt(inp,result,wi,f'V{wi+1}',apninger=inp.apninger),f'03-Snitt-V{wi+1}.pdf',f'Snitt V{wi+1}')
        add(tegn_veggoppstaltt(inp,result,wi,apninger=inp.apninger),f'04-Vegg-V{wi+1}.pdf',f'Veggoppstalt V{wi+1}')
    prod=tegn_produksjonsfigurer(inp,result)
    path=folder/'05-Produksjonstegninger.pdf';path.write_bytes(figurer_som_samlet_pdf(prod))
    for f in prod:plt.close(f)
    roompdf.append(path);manifest.append((str(path.relative_to(root)),'Alle produksjonselementer for beholdte vegger, tak og gulv'))
    model=open_model(inp);add(static3d(model,inp.navn),'06-3D-oversikt.pdf','3D-oversikt')
    model.write_html(str(folder/'06-3D-interaktiv.html'),include_plotlyjs=True)
    data=gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,inp.dorer,inp.rom_type,inp.panelbredde_m,apninger=inp.apninger,excluded_walls=inp.excluded_walls)
    (folder/'07-Modell.ifc').write_bytes(data)
    for kind in ('alle','materialer'):(folder/('08-Kapplister.pdf' if kind=='alle' else '09-Materialliste.pdf')).write_bytes(cutting_pdf([room],kind))
    merge(roompdf,folder/'00-Alle-tegninger.pdf');allroompdf.append(folder/'00-Alle-tegninger.pdf')
    world=world_input(room)
    for trace in open_model(world).data:combined.add_trace(trace)
    world_ifc=gen_ifc(world.pts,world.hoyde_m,world.navn,world.panel_key,world.dorer,world.rom_type,world.panelbredde_m,apninger=world.apninger,excluded_walls=world.excluded_walls)
    target=root/'03-Sammenstilling';target.mkdir(exist_ok=True);(target/f'{name}-felles-koordinater.ifc').write_bytes(world_ifc)
    print(name,'done',len(prod),'production pages',flush=True)
folder=root/'03-Sammenstilling'
savefig(assembly_plan(rooms),folder/'01-Sammenstilling-plan.pdf','Plantegning')
combined.update_layout(scene=dict(aspectmode='data',camera=dict(up=dict(x=0,y=0,z=1),projection=dict(type='orthographic'))),
    legend=dict(orientation='h',yanchor='top',y=-.03,xanchor='left',x=0),margin=dict(l=0,r=0,t=15,b=110),height=760)
combined.write_html(str(folder/'02-Sammenstilling-3D.html'),include_plotlyjs=True)
savefig(static3d(combined,'Tasty Fredrikstad – kjølerom og fryserom'),folder/'02-Sammenstilling-3D.pdf','Begge rom i 3D')
merge([folder/'01-Sammenstilling-plan.pdf',folder/'02-Sammenstilling-3D.pdf']+allroompdf,folder/'00-Alle-prosjekttegninger.pdf')
(folder/'03-Kapplister-hele-prosjektet.pdf').write_bytes(cutting_pdf(rooms,'alle'))
(folder/'04-Materialliste-hele-prosjektet.pdf').write_bytes(cutting_pdf(rooms,'materialer'))
cargo=packages(rooms);placed,missing=pack_floor(cargo,13600,2450,2700)
load_figure(placed,13600,2450,2700).write_html(str(folder/'05-Transport-3D.html'),include_plotlyjs=True)
transport_manifest(cargo,placed).to_csv(folder/'05-Transportliste.csv',index=False,encoding='utf-8-sig')
(root/'Tasty-Fredrikstad-prosjekt.json').write_bytes(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
(root/'LES-MEG.txt').write_text('Tasty Fredrikstad – tegningsleveranse 27.10.2026 – revisjon 10\n\nÅpne 03-Sammenstilling/00-Alle-prosjekttegninger.pdf for samlet tegningshefte.\nSeparate rom ligger i 01-Kjolerom og 02-Fryserom.\nKjølerom: 8960 x 8910 mm utvendige totalmål, V3 6410 mm, 80 mm panel. Fryserom: 3910 x 7460 mm utvendig, 3710 x 7260 mm innvendig, 100 mm panel. Veggpanelhøyde 2400 mm.\nKjølerom V4/V5 bruker fryserommets vegger: ingen separate kjøleromselementer eller oppstalter for disse veggene. Rom alene betyr utsnitt av dette prosjektet, ikke ombygget frittstående rom.\nFryserom: 22 mm lekter, 100 mm gulvpanel, vegger oppå gulvpanelet, 12 mm gulvplate, råformat 1500 × 3000 mm. Gulvfesting med vinkelbeslag.\nIFC i rommappene har lokal origo; IFC i sammenstillingsmappen har felles prosjektkoordinater og kan åpnes sammen. IFC inneholder ikke alle småbeslag/skruer.\nTak vises gjennomsiktig med grå skravering. 3D HTML kan åpnes uten nett. PDF-mål er påskrevet; ikke mål direkte på utskriften.\nTransport er et geometrisk forslag med foreløpige emballasjemål. Manglende kollivekter, støtte, aksellast og lastsikring må kontrolleres.\n',encoding='utf-8')
(folder/'05-Transport-status.txt').write_text(f'{len(placed)} av {len(cargo)} kolli er plassert i forslaget.\n{len(missing)} kolli er ikke plassert; alle står i transportlisten med status.\n{cargo.Vekt_kg.isna().sum()} kolli mangler vekt. Emballasjevekt og tilbehør uten oppgitt mengde er ikke inkludert.\n',encoding='utf-8')
checks=[]
for path in root.rglob('*.pdf'):
 reader=PdfReader(path);assert len(reader.pages)>0
 checks.append(dict(file=str(path.relative_to(root)),pages=len(reader.pages),bytes=path.stat().st_size))
(root/'filkontroll.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8')
print('COMPLETE',len(checks),'PDF files',sum(x['pages'] for x in checks),'pages including merged copies',flush=True)

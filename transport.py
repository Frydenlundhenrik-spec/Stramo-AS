"""Element and trim packages, loaded from the front of the trailer backwards."""
import math
import pandas as pd
import plotly.graph_objects as go
from purchase_summary import grouped_panels
from cutlist_pdf import project_materials


def packages(rooms):
    rows=[]
    def add(name, qty, l,w,h,kg=None,note='Foreløpig emballasjemål – kontroller'):
        rows.append(dict(Kolli=f'K{len(rows)+1}',Innhold=name,Antall=qty,Lengde_mm=int(l),Bredde_mm=int(w),Høyde_mm=int(h),Vekt_kg=kg,Grunnlag=note))
    for _,p in grouped_panels(rooms).iterrows():
        per = {80: 14, 100: 11}.get(p.Tykkelse_mm, max(1, int(1120 // p.Tykkelse_mm)))
        remaining=int(p.Bestill_hele_elementer)
        while remaining:
            n=min(per,remaining);remaining-=n
            add(f'{p.Panel} · {p.Leveringslengde_mm:g} × {p.Bredde_mm:g}',n,p.Leveringslengde_mm,p.Bredde_mm,150+n*p.Tykkelse_mm,
                p.Bestill_vekt_kg*n/p.Bestill_hele_elementer,
                f'Maks. {per} elementer per pakke; 150 mm underlag/emballasje i høyden. Panelvekt uten emballasje.')
    for _,r in project_materials(rooms).iterrows():
        if r.Gruppe!='Beslag':continue
        n=int(r.Stk)
        size=150 if '150' in r.Produkt else 100
        side=math.ceil(math.sqrt(n))*size
        add(r.Produkt,n,2540,side,side+50)
    return pd.DataFrame(rows)


def pack_floor(frame, length, width, height, clearance=30, stack_panels=True):
    """Fill across at the front before stacking, at most two high on full support."""
    if min(length,width,height)<=0 or clearance<0:raise ValueError('Ugyldige trailermål eller klaring.')
    items=frame.to_dict('records')
    for r in items:
        if any(pd.isna(r[c]) or r[c]<=0 for c in ('Lengde_mm','Bredde_mm','Høyde_mm')):
            raise ValueError('Alle kolli må ha positive mål.')
    candidates=[]
    for sort in (lambda r:r['Lengde_mm']*r['Bredde_mm'],lambda r:max(r['Lengde_mm'],r['Bredde_mm']),lambda r:r['Bredde_mm']):
        free=[(0,0,0,length,width,height,0)];placed=[];missing=[]
        for r in sorted(items,key=lambda r:(str(r.get('Innhold','')).startswith('PIR'),sort(r)),reverse=True):
            choices=[]
            if r['Høyde_mm']<=height:
                for i,(x,y,z,l,w,h,level) in enumerate(free):
                    is_panel = str(r.get("Innhold","")).startswith("PIR")
                    if r["Høyde_mm"]>h or (level and not is_panel):continue
                    orientations = [(r['Lengde_mm'],r['Bredde_mm'])]
                    if not is_panel: orientations.append((r['Bredde_mm'],r['Lengde_mm']))
                    for a,b in orientations:
                        if a<=l and b<=w:choices.append((x,z,l*w-a*b,y,i,a,b))
            if not choices:missing.append(r);continue
            _,_,_,_,i,a,b=min(choices)
            x,y,z,l,w,h,level=free.pop(i)
            placed.append(dict(r,X_mm=x,Y_mm=y,Z_mm=z,Lastelengde_mm=a,Lastebredde_mm=b))
            # Disjoint guillotine rectangles with clearance between packages.
            if l>a+clearance:free.append((x+a+clearance,y,z,l-a-clearance,w,h,level))
            if w>b+clearance:free.append((x,y+b+clearance,z,a,w-b-clearance,h,level))
            if stack_panels and level == 0 and str(r.get("Innhold","")).startswith("PIR") and h>r["Høyde_mm"]:
                free.append((x,y,z+r["Høyde_mm"],a,b,h-r["Høyde_mm"],1))
        score=(len(missing),max((r['X_mm']+r['Lastelengde_mm'] for r in placed),default=0))
        candidates.append((score,placed,missing))
    _,placed,missing=min(candidates,key=lambda c:c[0])
    placed.sort(key=lambda r:(r['X_mm'],r['Z_mm'],r['Y_mm']))
    placed=[dict(Lastenr=number,**r) for number,r in enumerate(placed,1)]
    return pd.DataFrame(placed),pd.DataFrame(missing)


def load_figure(placed,length,width,height):
    fig=go.Figure()
    edges=[(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    def vertices(x,y,z,l,w,h):
        return [(x,y,z),(x+l,y,z),(x+l,y+w,z),(x,y+w,z),(x,y,z+h),(x+l,y,z+h),(x+l,y+w,z+h),(x,y+w,z+h)]
    box=vertices(0,0,0,length,width,height)
    xyz=[box[i] if i is not None else (None,None,None) for edge in edges for i in (*edge,None)]
    fig.add_trace(go.Scatter3d(x=[p[0] for p in xyz],y=[p[1] for p in xyz],z=[p[2] for p in xyz],mode='lines',line=dict(color='#374151',width=3),name='Trailer'))
    palette=['#2a7f9e','#d9a441','#688f4e','#9569ac']
    for k,r in enumerate(placed.to_dict('records')):
        v=vertices(r['X_mm'],r['Y_mm'],r['Z_mm'],r['Lastelengde_mm'],r['Lastebredde_mm'],r['Høyde_mm'])
        fig.add_trace(go.Mesh3d(x=[p[0] for p in v],y=[p[1] for p in v],z=[p[2] for p in v],
            i=[0,0,4,4,0,0,1,1,2,2,3,3],j=[1,2,5,6,1,5,2,6,3,7,0,4],k=[2,3,6,7,5,4,6,5,7,6,4,7],
            color=palette[k%len(palette)],opacity=.85,name=r['Kolli'],text=f"{r['Kolli']}: {r['Innhold']} ({r['Antall']} stk)",hoverinfo='text',showlegend=False))
    fig.update_layout(scene=dict(aspectmode='data',xaxis_title='Fra front mot bakdører (mm)',yaxis_title='Bredde (mm)',zaxis_title='Høyde (mm)',
        annotations=[dict(x=x,y=width/2,z=height,text=label,showarrow=False,font=dict(size=14,color='#374151'))
                     for x,label in ((0,'FRONT'),(length,'BAKDØRER'))],
        camera=dict(eye=dict(x=1.6,y=-2,z=2.6),up=dict(x=0,y=0,z=1))),height=620,margin=dict(l=0,r=0,t=0,b=0))
    return fig


def transport_manifest(cargo, placed):
    """Include every package, including packages that do not fit the proposal."""
    manifest = cargo.copy()
    manifest['Status'] = manifest.Kolli.isin(placed.get('Kolli', [])).map({True:'Plassert',False:'Ikke plassert'})
    manifest=manifest.merge(placed.reindex(columns=['Kolli','Lastenr','X_mm','Y_mm','Z_mm','Lastelengde_mm','Lastebredde_mm']),on='Kolli',how='left')
    manifest['Lastenr']=manifest.Lastenr.astype('Int64')
    return manifest.sort_values('Lastenr',na_position='last').reset_index(drop=True)


def transport_ui(rooms):
    import streamlit as st
    st.header('Transport – lasteforslag')
    st.caption('Elementer og beslag. To panelpakker i bredden og opptil to i høyden når trailermålene tillater det. Last fra fronten av traileren (0 mm) og bakover mot bakdørene, i nummerert lasterekkefølge.')
    if not rooms:st.info('Legg til ferdige rom først.');return
    labels={r['id']:r['input']['navn'] for r in rooms}
    chosen=st.multiselect('Rom som skal transporteres',list(labels),default=list(labels),format_func=labels.get,key='transport_rooms')
    selected=[r for r in rooms if r['id'] in chosen]
    if not selected:st.info('Velg minst ett rom.');return
    c=st.columns(4)
    length=c[0].number_input('Innvendig lengde (mm)',min_value=1000,value=13600,step=100)
    width=c[1].number_input('Innvendig bredde (mm)',min_value=500,value=2450,step=50)
    height=c[2].number_input('Innvendig høyde (mm)',min_value=500,value=2700,step=50)
    payload=c[3].number_input('Tillatt nyttelast (kg)',min_value=100,value=24000,step=500)
    clearance=st.number_input('Klaring mellom kolli (mm)',min_value=0,max_value=500,value=30,step=10)
    st.caption('80 mm: maks. 14 elementer + 150 mm underlag/emballasje = 1270 mm pakkehøyde. 100 mm: maks. 11 elementer + 150 mm = 1250 mm. Delpakker får høyde etter faktisk antall. Panelpakker lastes i lengderetningen, maksimalt to oppå hverandre. Fire pakker à 2400 mm bruker 2400 mm lastelengde når to får plass i bredden og to i høyden. Klaring gjelder mellom kolli på samme nivå. Emballasjemål og ukjente vekter kan endres nedenfor.')
    stack_panels=st.checkbox('Tillat to panelpakker i høyden med full understøttelse',value=True)
    base=packages(selected)
    import hashlib
    revision=hashlib.sha256(base.to_json().encode()).hexdigest()[:12]
    edited=st.data_editor(base,hide_index=True,disabled=['Kolli','Innhold','Antall','Grunnlag'],key='cargo_'+revision)
    try:placed,missing=pack_floor(edited,length,width,height,clearance,stack_panels)
    except ValueError as exc:st.error(str(exc));return
    weight=pd.to_numeric(edited.Vekt_kg,errors='coerce')
    if (weight.dropna()<0).any():st.error('Vekt kan ikke være negativ.');return
    a,b,c,d=st.columns(4)
    a.metric('Plasserte kolli',f'{len(placed)} / {len(edited)}')
    area=sum(r['Lastelengde_mm']*r['Lastebredde_mm'] for r in placed.to_dict('records') if r['Z_mm']==0)
    b.metric('Utnyttet gulvareal',f'{100*area/(length*width):.1f} %')
    c.metric('Registrert vekt',f'{weight.sum():,.0f} kg')
    used_length = max((r['X_mm']+r['Lastelengde_mm'] for r in placed.to_dict('records')), default=0)
    d.metric('Brukt lastelengde', f'{used_length:.0f} mm')
    if weight.isna().any():st.warning('Total transportvekt er ufullstendig: legg inn vekt for kolli uten vekt. Panelvekten omfatter ikke emballasje.')
    if weight.sum()>payload:st.error('Registrert vekt overstiger tillatt nyttelast.')
    if not missing.empty:
        st.warning('Disse kolliene fikk ikke plass i forslaget. Juster pakking/stabling eller bruk en ekstra trailer.')
        st.dataframe(missing,hide_index=True)
    fig=load_figure(placed,length,width,height);st.plotly_chart(fig,use_container_width=True)
    st.caption('Geometrisk lasteforslag. Kontroller emballasje, tillatt stabling, støtte under lange paneler, aksellast og lastsikring før lasting. Forslaget er ikke en kontroll av aksellast eller lastsikring.')
    st.dataframe(placed,hide_index=True)
    manifest=transport_manifest(edited,placed)
    st.download_button('Last ned transportliste CSV',manifest.to_csv(index=False).encode('utf-8-sig'),'transportliste.csv','text/csv')
    st.download_button('Last ned lasteforslag i 3D',fig.to_html(include_plotlyjs=True).encode('utf-8'),'transport-3d.html','text/html')

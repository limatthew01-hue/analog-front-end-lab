"""Build and route the board with KiCad's pcbnew Python API (KiCad 7+).

The final editable .kicad_pcb is authoritative. This deterministic grid router
is deliberately conservative; KiCad DRC remains the acceptance check.
"""
from pathlib import Path
import csv, heapq, json, math, os
import pcbnew as pcb

ROOT=Path(__file__).resolve().parents[1]
design=json.loads((ROOT/'design.json').read_text())
LIB=Path(os.environ.get('KICAD_FOOTPRINT_DIR','/usr/share/kicad/footprints'))
os.environ.setdefault('KICAD7_FOOTPRINT_DIR',str(LIB))
board=pcb.BOARD()
board.SetCopperLayerCount(2)
board.GetDesignSettings().SetCopperLayerCount(2)
def pt(x,y): return pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y))
def mm(p): return (pcb.ToMM(p.x),pcb.ToMM(p.y))
net_names=sorted({n for c in design['components'] for n in c['nets'].values()})
nets={}
for name in net_names:
    net=pcb.NETINFO_ITEM(board,name); board.Add(net); nets[name]=net
pad_records=[]
footprints=[]
for component in design['components']:
    library,name=component['footprint'].split(':')
    fp=pcb.FootprintLoad(str(LIB/(library+'.pretty')),name)
    if fp is None: raise RuntimeError(component['footprint'])
    fp.SetReference(component['ref']); fp.SetValue(component['value'])
    fp.SetFPID(pcb.LIB_ID(library,name))
    board.Add(fp)
    x,y,angle=component['at']; fp.SetPosition(pt(x,y)); fp.SetOrientationDegrees(angle)
    fp.Value().SetVisible(False)
    fp.Reference().SetTextSize(pt(.9,.9)); fp.Reference().SetTextThickness(pcb.FromMM(.15))
    for pad in fp.Pads():
        pad.SetNet(nets[component['nets'][pad.GetNumber()]])
        pad_records.append((component['ref'],pad))
    footprints.append(fp)
for i,(x,y) in enumerate(design['holes'],1):
    fp=pcb.FootprintLoad(str(LIB/'MountingHole.pretty'),'MountingHole_3.2mm_M3')
    fp.SetFPID(pcb.LIB_ID('MountingHole','MountingHole_3.2mm_M3'))
    board.Add(fp); fp.SetPosition(pt(x,y)); fp.SetReference('H'+str(i)); fp.Value().SetVisible(False)
    fp.Reference().SetVisible(False)
    for pad in fp.Pads(): pad_records.append(('H'+str(i),pad))
for a,b in [((0,0),(60,0)),((60,0),(60,40)),((60,40),(0,40)),((0,40),(0,0))]:
    shape=pcb.PCB_SHAPE(board); shape.SetShape(pcb.SHAPE_T_SEGMENT)
    shape.SetStart(pt(*a)); shape.SetEnd(pt(*b)); shape.SetLayer(pcb.Edge_Cuts)
    shape.SetWidth(pcb.FromMM(.05)); board.Add(shape)
def text(label,x,y,size=1):
    t=pcb.PCB_TEXT(board); t.SetText(label); t.SetPosition(pt(x,y)); t.SetLayer(pcb.F_SilkS)
    t.SetTextSize(pt(size,size)); t.SetTextThickness(pcb.FromMM(.15)); board.Add(t)
text('DUAL SENSOR INTERFACE',30,4.5,1.3)
text('Matthew Li / REV A / 3.3V ONLY',30,36,1)
text('IN0 0-6V',10,7); text('IN1 0-6V',10,24)
for label,y in [('3V3',17),('GND',19.54),('A0',22.08),('A1',24.62)]: text(label,57,y,.8)

# Rasterize copper with clearance and a grid discretization allowance.
STEP=.2; W=301; H=201; L=W*H
blocked=[[0]*L for _ in range(2)]
pad_boxes=[]; through=set(); vias=[]
def index(x,y): return y*W+x
def grid(x,y): return (round(x/STEP),round(y/STEP))
def box_stamp(layer,x0,y0,x1,y1,bit):
    for y in range(max(0,math.floor(y0/STEP)),min(H,math.ceil(y1/STEP)+1)):
        for x in range(max(0,math.floor(x0/STEP)),min(W,math.ceil(x1/STEP)+1)):
            blocked[layer][index(x,y)] |= bit
def circle_stamp(layer,x,y,r,bit):
    for gy in range(max(0,math.floor((y-r)/STEP)),min(H,math.ceil((y+r)/STEP)+1)):
        for gx in range(max(0,math.floor((x-r)/STEP)),min(W,math.ceil((x+r)/STEP)+1)):
            if (gx*STEP-x)**2+(gy*STEP-y)**2<=r*r:
                blocked[layer][index(gx,gy)] |= bit
for layer in range(2):
    for y in range(H):
        for x in range(W):
            if min(x*STEP,y*STEP,60-x*STEP,40-y*STEP)<.8: blocked[layer][index(x,y)]=1
for ref,pad in pad_records:
    bbox=pad.GetBoundingBox(); x0,y0=mm(bbox.GetPosition()); x1=x0+pcb.ToMM(bbox.GetWidth()); y1=y0+pcb.ToMM(bbox.GetHeight())
    net=pad.GetNetCode(); bit=1<<net if net else 1
    pad_boxes.append((x0,y0,x1,y1))
    layers=[0,1] if pad.GetAttribute()!=pcb.PAD_ATTRIB_SMD else [0]
    for layer in layers: box_stamp(layer,x0-.47,y0-.47,x1+.47,y1+.47,bit)
    if pad.GetAttribute()==pcb.PAD_ATTRIB_PTH: through.add(grid(*mm(pad.GetPosition())))

def allowed(layer,x,y,bit):
    return 0<=x<W and 0<=y<H and not(blocked[layer][index(x,y)]&~bit)
def via_allowed(x,y,bit):
    px,py=x*STEP,y*STEP
    if (x,y) in through: return True
    if any(x0-.5<=px<=x1+.5 and y0-.5<=py<=y1+.5 for x0,y0,x1,y1 in pad_boxes): return False
    return all(allowed(layer,x+dx,y+dy,bit) for layer in [0,1] for dx in [-2,0,2] for dy in [-2,0,2])
def route(start,end,net):
    bit=1<<net
    sx,sy=grid(*start); tx,ty=grid(*end)
    origin=(0,sx,sy); goal=(0,tx,ty)
    def h(node):
        layer,x,y=node; dx=abs(x-tx); dy=abs(y-ty)
        return 10*max(dx,dy)+4*min(dx,dy)+(10 if layer else 0)
    frontier=[(h(origin),0,origin)]; best={origin:0}; prev={}
    while frontier:
        _,cost,node=heapq.heappop(frontier)
        if cost!=best[node]: continue
        if node==goal:
            path=[node]
            while node!=origin: node=prev[node]; path.append(node)
            return path[::-1]
        layer,x,y=node
        candidates=[]
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            nx,ny=x+dx,y+dy
            if allowed(layer,nx,ny,bit): candidates.append(((layer,nx,ny),14 if dx and dy else 10))
        if via_allowed(x,y,bit) and allowed(1-layer,x,y,bit):
            candidates.append(((1-layer,x,y),1 if (x,y) in through else 80))
        for nxt,extra in candidates:
            new=cost+extra
            if new<best.get(nxt,10**12):
                best[nxt]=new; prev[nxt]=node; heapq.heappush(frontier,(new+h(nxt),new,nxt))
    raise RuntimeError(f'Cannot route net {net}: {start} to {end}')

def add_track(a,b,layer,net):
    if a==b: return
    t=pcb.PCB_TRACK(board); t.SetStart(pt(*a)); t.SetEnd(pt(*b)); t.SetWidth(pcb.FromMM(.25))
    t.SetLayer(pcb.F_Cu if layer==0 else pcb.B_Cu); t.SetNetCode(net); board.Add(t)
    dist=math.hypot(b[0]-a[0],b[1]-a[1]); n=max(1,math.ceil(dist/(STEP/2)))
    for i in range(n+1): circle_stamp(layer,a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n,.6,1<<net)
connections=0
# Short signal nets first; ground last. Existing same-net copper is traversable.
order=sorted(net_names,key=lambda n:(n=='GND',len([p for _,p in pad_records if p.GetNetname()==n]),n))
for name in order:
    pads=[p for _,p in pad_records if p.GetNetname()==name]
    connected=[mm(pads.pop(0).GetPosition())]
    while pads:
        _,pi,target=min((math.dist(a,mm(p.GetPosition())),i,a) for i,p in enumerate(pads) for a in connected)
        start=mm(pads.pop(pi).GetPosition()); path=route(start,target,nets[name].GetNetCode())
        net=nets[name].GetNetCode()
        add_track(start,(path[0][1]*STEP,path[0][2]*STEP),0,net)
        k=0
        while k<len(path)-1:
            layer,x,y=path[k]; nxt=path[k+1]
            if nxt[0]!=layer:
                if (x,y) not in through:
                    via=pcb.PCB_VIA(board); via.SetPosition(pt(x*STEP,y*STEP)); via.SetWidth(pcb.FromMM(.6))
                    via.SetDrill(pcb.FromMM(.3)); via.SetViaType(pcb.VIATYPE_THROUGH)
                    via.SetLayerPair(pcb.F_Cu,pcb.B_Cu); via.SetNetCode(net); board.Add(via); vias.append((x,y))
                    for lay in [0,1]: circle_stamp(lay,x*STEP,y*STEP,.8,1<<net)
                k+=1; continue
            dx,dy=nxt[1]-x,nxt[2]-y; end=k+1
            while end+1<len(path) and path[end+1][0]==layer and (path[end+1][1]-path[end][1],path[end+1][2]-path[end][2])==(dx,dy): end+=1
            add_track((x*STEP,y*STEP),(path[end][1]*STEP,path[end][2]*STEP),layer,net); k=end
        add_track((path[-1][1]*STEP,path[-1][2]*STEP),target,0,net)
        connected.append(start); connections+=1
        print('Routed',name,flush=True)

# A stitched/routed ground network also has a B.Cu return plane.
zone=pcb.ZONE(board); zone.SetLayer(pcb.B_Cu); zone.SetNet(nets['GND'])
zone.SetLocalClearance(pcb.FromMM(.25)); zone.SetThermalReliefGap(pcb.FromMM(.3)); zone.SetThermalReliefSpokeWidth(pcb.FromMM(.3))
outline=zone.Outline(); outline.NewOutline()
for x,y in [(1,1),(59,1),(59,39),(1,39)]: outline.Append(pcb.FromMM(x),pcb.FromMM(y))
board.Add(zone)
pcb.SaveBoard(str(ROOT/'sensor-interface.kicad_pcb'),board)
print('Saved routed board; loading project context for zone fill.',flush=True)
board=pcb.LoadBoard(str(ROOT/'sensor-interface.kicad_pcb'))
pcb.ZONE_FILLER(board).Fill(board.Zones())
print('Filled ground plane.',flush=True)
board.BuildConnectivity()
pcb.SaveBoard(str(ROOT/'sensor-interface.kicad_pcb'),board)
(ROOT/'results').mkdir(exist_ok=True)
pcb.WriteDRCReport(board,str(ROOT/'results/drc.txt'),pcb.EDA_UNITS_MILLIMETRES,False)
metrics={'kicad':pcb.GetBuildVersion(),'width_mm':60,'height_mm':40,'layers':2,
         'electrical_components':len(design['components']),'mounting_holes':4,'nets':len(nets),
         'routed_connections':connections,'vias':len(vias),'track_width_mm':.25,
         'via_diameter_mm':.6,'via_drill_mm':.3}
(ROOT/'results/layout.json').write_text(json.dumps(metrics,indent=2)+'\n')
with (ROOT/'bom.csv').open('w',newline='') as f:
    writer=csv.writer(f); writer.writerow(['Reference','Value / requirement','Footprint'])
    for c in design['components']: writer.writerow([c['ref'],c['value'],c['footprint']])
print(json.dumps(metrics))

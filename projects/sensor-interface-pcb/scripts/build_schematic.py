"""Generate an editable, self-contained KiCad 7 schematic from design.json."""
from pathlib import Path
import json,uuid
ROOT=Path(__file__).resolve().parents[1]
design=json.loads((ROOT/'design.json').read_text())
def uid(key): return str(uuid.uuid5(uuid.NAMESPACE_URL,'matthew-li/sensor-interface/'+key))
def q(value): return json.dumps(str(value))
def effects(size=1,extra=''): return f'(effects (font (size {size} {size})) {extra})'
def pin(number,name,x,y,angle,kind='passive',length=2.54):
    return f'(pin {kind} line (at {x} {y} {angle}) (length {length}) (name {q(name)} {effects(.8)}) (number {q(number)} {effects(.8)}))'
def definition(kind,body,pins,prefix):
    name='Sensor:'+kind
    props=f'(property "Reference" "{prefix}" (at 0 3 0) {effects()}) (property "Value" "{kind}" (at 0 -3 0) {effects()})'
    return f'(symbol {q(name)} (pin_names (offset .5)) (in_bom yes) (on_board yes) {props} (symbol "{kind}_0_1" {body}) (symbol "{kind}_1_1" {" ".join(pins)}))'
rect='(rectangle (start -2.54 -1.016) (end 2.54 1.016) (stroke (width .254) (type default)) (fill (type none)))'
symbols=[definition('resistor',rect,[pin(1,'~',-5.08,0,0),pin(2,'~',5.08,0,180)],'R')]
cap=' '.join(f'(polyline (pts (xy {x} -1.778) (xy {x} 1.778)) (stroke (width .254) (type default)) (fill (type none)))' for x in [-.762,.762])
symbols.append(definition('capacitor',cap,[pin(1,'~',-5.08,0,0,length=4.318),pin(2,'~',5.08,0,180,length=4.318)],'C'))
rectbig='(rectangle (start -10.16 10.16) (end 10.16 -10.16) (stroke (width .254) (type default)) (fill (type background)))'
opins=[pin(1,'OUT_A',-12.7,7.62,0,'output'),pin(2,'IN_A-',-12.7,2.54,0,'input'),pin(3,'IN_A+',-12.7,-2.54,0,'input'),pin(4,'VSS',-12.7,-7.62,0,'power_in'),
       pin(8,'VDD',12.7,7.62,180,'power_in'),pin(7,'OUT_B',12.7,2.54,180,'output'),pin(6,'IN_B-',12.7,-2.54,180,'input'),pin(5,'IN_B+',12.7,-7.62,180,'input')]
symbols.append(definition('opamp',rectbig,opins,'U'))
for count in [2,4]:
    ys=[2.54,-2.54] if count==2 else [7.62,2.54,-2.54,-7.62]
    body=f'(rectangle (start -2.54 {max(ys)+2.54}) (end 4 {-max(ys)-2.54}) (stroke (width .254) (type default)) (fill (type background)))'
    names=['IN','GND'] if count==2 else ['3V3','GND','ADC0','ADC1']
    pins=[pin(i+1,n,-5.08,y,0,'power_out' if count==4 and i<2 else 'passive') for i,(y,n) in enumerate(zip(ys,names))]
    symbols.append(definition('header'+str(count),body,pins,'J'))

positions={'J2':(27,43),'R1':(65,38),'R2':(65,55),'J3':(27,92),'R3':(65,87),'R4':(65,104),
           'U1':(140,75),'R5':(195,43),'C2':(235,43),'R6':(195,101),'C3':(235,101),
           'C1':(130,123),'C4':(175,123),'J1':(242,147)}
rootid=uid('sheet')
items=[]
for c in design['components']:
    ref=c['ref']; kind=c['kind']; x,y=positions[ref]
    value='MCU HARNESS' if ref=='J1' else c['value']
    props=' '.join([f'(property "Reference" {q(ref)} (at {x} {y-5 if kind not in ["opamp","header4","header2"] else y-14} 0) {effects()})',
                    f'(property "Value" {q(value)} (at {x} {y+4 if kind not in ["opamp","header4","header2"] else y+14} 0) {effects(.95)})',
                    f'(property "Footprint" {q(c["footprint"])} (at {x} {y} 0) {effects(1,"hide")})'])
    if kind in ['resistor','capacitor']: pins={'1':(-5.08,0),'2':(5.08,0)}
    elif kind=='opamp': pins={'1':(-12.7,-7.62),'2':(-12.7,-2.54),'3':(-12.7,2.54),'4':(-12.7,7.62),'8':(12.7,-7.62),'7':(12.7,-2.54),'6':(12.7,2.54),'5':(12.7,7.62)}
    else:
        ys=[-2.54,2.54] if kind=='header2' else [-7.62,-2.54,2.54,7.62]
        pins={str(i+1):(-5.08,dy) for i,dy in enumerate(ys)}
    pin_ids=' '.join(f'(pin {q(n)} (uuid {uid(ref+"/"+n)}))' for n in pins)
    items.append(f'(symbol (lib_id "Sensor:{kind}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (uuid {uid(ref)}) {props} {pin_ids} (instances (project "sensor-interface" (path "/{rootid}" (reference {q(ref)}) (unit 1)))))')
    for number,(dx,dy) in pins.items():
        px,py=x+dx,y+dy; ex=px+(-5.08 if dx<0 else 5.08)
        items.append(f'(wire (pts (xy {px:.3f} {py:.3f}) (xy {ex:.3f} {py:.3f})) (stroke (width 0) (type default)) (uuid {uid(ref+number+"wire")}))')
        justify='right bottom' if dx<0 else 'left bottom'
        items.append(f'(label {q(c["nets"][number])} (at {ex:.3f} {py:.3f} 0) {effects(.95,f"(justify {justify})")} (uuid {uid(ref+number+"label")}))')
notes=[(20,16,'DUAL-CHANNEL SENSOR INTERFACE / REV A',2.5),
       (20,23,'Two 0-6 V inputs / MCP6002 unity buffers / 10k + 1uF output filters',1.3),
       (20,143,'Design operating range: 0 to 6 V relative to GND. Supply: regulated 3.3 V only.',1.2),
       (20,150,'J1 pins: 1=3V3, 2=GND, 3=ADC0, 4=ADC1. External MCU: NUCLEO-F401RE.',1.2),
       (20,157,'Divider gain: 0.5 nominal. Filter cutoff: 15.9 Hz nominal. ADC sample rate: 100 Hz.',1.2),
       (20,164,'Net labels connect matching names. U1 output pins loop back to their inverting inputs.',1.2),
       (20,171,'Prototype design: not fabricated or bench tested. Disconnect inputs when board power is off.',1.2)]
for i,(x,y,txt,size) in enumerate(notes): items.append(f'(text {q(txt)} (at {x} {y} 0) {effects(size,"(justify left)")} (uuid {uid("note"+str(i))}))')
content=f'(kicad_sch (version 20230121) (generator eeschema) (uuid {rootid}) (paper "A4") (title_block (title "Dual-channel sensor interface") (rev "A") (company "Matthew Li") (comment 1 "3.3 V prototype / hardware validation pending")) (lib_symbols {" ".join(symbols)}) {" ".join(items)})\n'
(ROOT/'sensor-interface.kicad_sch').write_text(content)
libs=['Resistor_SMD','Capacitor_SMD','Package_SO','Connector_PinHeader_2.54mm','MountingHole']
(ROOT/'fp-lib-table').write_text('(fp_lib_table\n'+''.join(f' (lib (name "{lib}")(type "KiCad")(uri "${{KICAD7_FOOTPRINT_DIR}}/{lib}.pretty")(options "")(descr "KiCad standard library"))\n' for lib in libs)+')\n')
project={'meta':{'filename':'sensor-interface.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.25,'min_via_diameter':.6,'min_through_hole_diameter':.3,'min_copper_edge_clearance':.5}}}}
(ROOT/'sensor-interface.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
print('Wrote schematic, footprint table and project rules.')

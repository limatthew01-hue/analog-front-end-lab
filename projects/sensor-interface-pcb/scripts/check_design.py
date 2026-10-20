"""Compare schematic XML connectivity and PCB copper pads to design.json."""
from pathlib import Path
import json,re,xml.etree.ElementTree as ET
import pcbnew
ROOT=Path(__file__).resolve().parents[1]
design=json.loads((ROOT/'design.json').read_text())
expected={}
for c in design['components']:
    for pin,net in c['nets'].items(): expected.setdefault(net,set()).add((c['ref'],pin))
schematic={}
for net in ET.parse(ROOT/'results/schematic.net').findall('.//nets/net'):
    schematic[net.attrib['name'].lstrip('/') ]={(n.attrib['ref'],n.attrib['pin']) for n in net.findall('node')}
assert schematic==expected, 'Schematic net membership differs from declared design'
board=pcbnew.LoadBoard(str(ROOT/'sensor-interface.kicad_pcb'))
pcbnew.WriteDRCReport(board,str(ROOT/'results/drc.txt'),pcbnew.EDA_UNITS_MILLIMETRES,False)
actual={}
for fp in board.GetFootprints():
    if fp.GetReference().startswith('H'): continue
    for pad in fp.Pads(): actual.setdefault(pad.GetNetname(),set()).add((fp.GetReference(),pad.GetNumber()))
assert actual==expected, 'PCB pad mapping differs from schematic'
report=(ROOT/'results/drc.txt').read_text()
for line in ['Found 0 DRC violations','Found 0 unconnected pads','Found 0 Footprint errors']:
    assert line in report,line
result={'electrical_components':len(design['components']),'verified_pin_connections':sum(map(len,expected.values())),
        'nets':len(expected),'schematic_to_board_match':True,'drc_violations':0,'unconnected_pads':0,
        'footprint_errors':0,'erc':'Not run: KiCad 7 CLI has no ERC command. Netlist membership checked separately.'}
(ROOT/'results/verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

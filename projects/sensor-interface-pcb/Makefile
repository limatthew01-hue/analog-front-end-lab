PYTHON_KICAD ?= python3
PYTHON ?= python3
KICAD_CLI ?= kicad-cli
.PHONY: regenerate check export analyze
regenerate:
	$(PYTHON) scripts/build_schematic.py
	$(PYTHON_KICAD) scripts/build_board.py
check:
	$(KICAD_CLI) sch export netlist --format kicadxml --output results/schematic.net sensor-interface.kicad_sch
	$(PYTHON_KICAD) scripts/check_design.py
export:
	$(KICAD_CLI) pcb export gerbers --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask --output fabrication/ sensor-interface.kicad_pcb
	$(KICAD_CLI) pcb export drill --output fabrication/ sensor-interface.kicad_pcb
	$(KICAD_CLI) pcb export svg --layers F.Cu,B.Cu,F.Silkscreen,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet --output docs/board.svg sensor-interface.kicad_pcb
	$(KICAD_CLI) sch export svg --output docs --exclude-drawing-sheet sensor-interface.kicad_sch
analyze:
	$(PYTHON) scripts/analyze.py --ngspice ngspice

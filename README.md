# SI-LLM

Super Intelligence Large Language Model for the hardware loop.

Branch: `si-llm`

## What it covers

- **PCB** — requirements, schematic intent, netlist, placement, routing, DRC, stackup, Gerber list, BOM
- **CAD** — parametric solid, feature tree, mass, STEP-style feature script
- **CAM** — tool, feed, spindle, stepdown, contour + bore G-code
- **3D print** — PLA / PETG / ABS / resin, infill, walls, supports, time and filament
- **Simulation** — thermal rise, von Mises vs load, insertion loss

## Modalities

Text, voice (browser speech in and out), and vision (image read + label correction).

## Train, improve, analyze

Lessons update a local adapter: copper clearance, trace width, safety factor, print material, CAM feed scale. Rated replies feed the analyze desk.

The interactive studio runs beside this repository. This branch is the named home for the model.

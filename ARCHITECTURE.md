# SI-LLM architecture

SI-LLM is a small PCB specialist. It is not a general frontier model. A 22.3 million parameter transformer turns a short sentence into a command. Python code around that model holds the board catalogs, the calculators, the approval gate, and the MCP calls.

## How to run it

```bash
sh startup.sh
si "what is a buck converter"
```

`startup.sh` starts the model server and, the first time, installs the `si` command. After that you only type `si`.

| Piece | What it is | Where it listens |
| --- | --- | --- |
| `si` | Native client. It does not load the weights. | Your terminal |
| Model server | Python. Loads the checkpoint and decides the command. | `http://127.0.0.1:8765` |
| PCB tool server | MCP tools for the board. | `http://127.0.0.1:8766/mcp` |
| CAD tool server | MCP tools for the solid. | `http://127.0.0.1:8767/mcp` |

The web studio, when this workspace is running, is a second client of the same model server.

## Request path

```text
you
  → si                         native C++ or Rust client
  → POST /cli                  model server (py/si/server.py)
  → designer_turn              harness (py/si/mcp_client.py)
       1. knowledge graph      clearance, IPC, stackup answers
       2. board catalogs       power, robot, computer, sensor
       3. hear                 direct place / move / connect sentences
       4. transformer          only if the three above do not match
  → MCP tool call              PCB or CAD server, after the approval gate
  → reply text back to si
```

The transformer is the last step, not the first. Catalog and graph hits never call the network. That is deliberate: a 28-token model cannot store datasheets or IPC tables.

## Model specification

Saved checkpoint: `model/si.pt`. Measured record: `model/meta.json`.

| Item | Value |
| --- | --- |
| Name | `si-pcb-cad` |
| Family | Causal GPT, pre-norm |
| Parameters | 22,273,920 |
| Layers | 11 |
| Width | 384 |
| Heads | 8 (head size 48) |
| MLP | 384 → 1536 → 384, GELU |
| Dropout | 0.15 |
| Vocabulary | 3,572 word tokens, plus `<pad> <bos> <eos> <sep> <unk> <none>` |
| Context | 28 tokens (`BLOCK`) |
| Prompt limit at inference | 18 words, then `<sep>`, then up to 6 generated tokens |
| Decoding | Greedy. Token 1 must be an intent. Tokens 2–5 must be slot words. Token 6 is `<eos>`. |
| Optimizer | AdamW, learning rate `1e-3`, weight decay `0.01` |
| Batch | 48 |
| Device used for training | CPU, 4 threads |
| Seed | 7 |
| Best checkpoint | Epoch 3 |
| Held-out exact match | 0.966 |
| Held-out, after slot binding | 0.968 |
| Board-name subset | 0.975 |
| Training rows | 37,223 |
| Test rows | 3,062 |

The loss is cross-entropy on the tokens after `<sep>` only. The prompt tokens are ignored (`ignore_index=-100`).

A program looks like:

```text
<bos> place a resistor r1 at 10 12 <sep> PCB_ADD res r1 10 12 <eos>
```

`program_to_action` in `py/si/net.py` turns that program into `{op, ...}` for the tool planner.

## What the vocabulary covers

Words, not characters. Part numbers that are not in the list become `<unk>`.

- 55 intents (`PCB_ADD`, `POWER`, `COMPUTER`, `SENSOR`, `ROUTE`, …)
- Packages, reference designators, net names, numbers, industries, board classes
- Tokens exported by the four board catalogs

The `hear` parser (`py/si/hear.py`) covers the everyday sentences the vocabulary cannot hold: "place a resistor r1 at 10 12", "move u1 to 20 30", "connect gnd from c1 to u1".

## Training steps

Training data is generated, not downloaded. `samples()` in `py/si/net.py` builds prompt/program pairs from the catalogs and from sentence templates.

```bash
python3 -m py.si.net
```

That runs `train()`:

1. Build the vocabulary.
2. Generate rows. Seed 7.
3. Split. Compositional commands (`PCB_ADD`, `PCB_NET`, `CAD_SKETCH`, `SCH_ADD`, `SCH_WIRE`) send about 12% of groups to the test set. Every other command is repeated 12 times in training, with one row held out.
4. Train up to 4 epochs.
5. After each epoch, score the full held-out set and the board subset (`POWER`, `ROBOT`, `COMPUTER`, `SENSOR`).
6. Keep the checkpoint with the best board score, then held-out score.
7. Stop early if board accuracy is at least 0.99 after epoch 2.
8. Write `model/si.pt` (weights and the vocabulary list) and `model/meta.json`.

Do not start a training run unless you mean to replace `model/si.pt`. Inference only reads those two files.

## Harness

| File | Job |
| --- | --- |
| `py/si/server.py` | HTTP gateway. `/cli`, `/approve`, `/mode`, `/mcp/add`, `/mcp/remove`, `/health`, `/datasheet` |
| `py/si/mcp_client.py` | `designer_turn`. Order of match, approval, MCP dispatch |
| `py/si/graph.py` | Rule answers: clearance, creepage, trace width, stackup |
| `py/si/power.py` | Power-electronics board catalog |
| `py/si/robot.py` | Robotics board catalog |
| `py/si/computer.py` | Computer and motherboard catalog |
| `py/si/sensor.py` | Sensor and switch catalog |
| `py/si/hear.py` | Direct sentence to tool call |
| `py/si/net.py` | Model, training, `predict`, program to action |
| `py/si/engine.py` | Board state, parameters, tool execution against the session |
| `py/si/desk.py` | IPC-2221 style calculators and file writers |
| `py/si/datasheet.py` | Text datasheet to package guesses |
| `py/si/ipc.py` | IPC class and clearance tables used by the desk |
| `py/si/router.py` | Grid router used by the autoroute tool |
| `py/si/tool_server.py` | The PCB and CAD MCP servers |
| `py/si/cli.py` | Older Python client. Same server protocol. |

State is `model/session.json`. MCP connections for the model server are `model/mcp.json`. `SI_MODEL` overrides the model directory. If it is unset, the directory is `model/` next to the project.

## MCP and approval

Modes are `auto`, `semi`, and `man`.

- `auto` runs the tool.
- `semi` runs read-only tools and asks for the rest.
- `man` asks before every tool.

`si --yes "..."` sends `approved: true` for that one sentence. A yes / always / no answer goes to `POST /approve`.

```bash
si mcp add pcb --url http://127.0.0.1:8766/mcp
si mcp list
si mode semi
```

## Native client

Preferred build is macOS, from `native/xcode/si.xcodeproj`. The source is `native/xcode/si/main.cpp`. It is C++17 with no libraries. `startup.sh` compiles it with Xcode on a Mac, or with `g++` elsewhere, and copies it to `/usr/local/bin/si` or `~/.local/bin/si`.

`native/si/` is the same client in Rust, for the Linux and Windows builds in `.github/workflows/si-native.yml`. It speaks to the same model server. It does not contain the weights.

`SI_URL` changes the model server address. The default is `http://127.0.0.1:8765`.

## Web studio

`src/routes/index.tsx` is the studio. `src/lib/si/run.ts` calls the same model server from the server side. `src/components/si/llm-app.tsx` is the chat. The studio is optional. The CLI does not need it.

## Limits

- Context is 28 tokens. It is not a million-token model.
- It does not read a PDF scan. A datasheet must have selectable text.
- It does not run SPICE, a field solver, or a fabrication house.
- IPC figures in `desk.py` are open calculator bands, not a licensed copy of the standard.
- The native binary cannot answer if the Python server is down.
- Retraining on CPU takes a long time and replaces the checkpoint only when the board score improves.

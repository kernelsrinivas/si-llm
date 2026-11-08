# si-llm

A small PCB specialist. The `si` command sends a sentence to a Python server. That server runs a 168.6M-parameter model (11 think layers, 6 decision layers, 6 design layers) and the board catalogs, then calls MCP tools.

```bash
sh startup.sh
si "what is a buck converter"
```

Architecture, model numbers, and training steps: [ARCHITECTURE.md](ARCHITECTURE.md).

# si-llm

A small PCB specialist. The `si` command sends a sentence to a Python server. That server runs a 22.3M-parameter model and the board catalogs, then calls MCP tools.

```bash
sh startup.sh
si "what is a buck converter"
```

Architecture, model numbers, and training steps: [ARCHITECTURE.md](ARCHITECTURE.md).

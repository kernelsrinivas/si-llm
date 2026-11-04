"""Claude-style MCP client.

Add a connection, then approve each tool call.

    python3 -m py.si.cli mcp add pcb --url http://127.0.0.1:8766/mcp
    python3 -m py.si.cli mcp add board --command "python3 -m py.si.tool_server stdio pcb"
    python3 -m py.si.cli mcp list
    python3 -m py.si.cli --yes "place esp32 as u1 at 40 30"
"""

from __future__ import annotations

import sys

from py.si.mcp_client import add_server, decide, designer_turn, probe, remove_server, set_mode


def print_turn(body: dict) -> None:
    print(body["reply"])
    command = body["commands"][0] if body.get("commands") else ""
    if command:
        print(f"[{body['runtime']}] {command}")


def print_proposal(body: dict) -> None:
    print("SI-LLM wants to call an MCP tool")
    print()
    for call in body.get("calls") or []:
        print(f"  server  {call['server']}")
        print(f"  tool    {call['tool']}")
        for arg in call.get("args") or []:
            print(f"  {arg['key']:<8}{arg['value']}")
        print()


def approve_interactive(body: dict) -> dict:
    print_proposal(body)
    if not sys.stdin.isatty():
        print("Not sent. Pass --yes to allow once.")
        return body
    answer = input("Allow? [y]es / [a]lways / [n]o: ").strip().lower()
    decision = {"y": "allow", "yes": "allow", "a": "always", "always": "always"}.get(answer, "deny")
    return decide(str(body.get("proposalId") or ""), decision)


def mcp_command(argv: list[str]) -> int:
    if not argv or argv[0] in {"list", "ls"}:
        rows = probe()
        if not rows:
            print("No MCP connections. Add one with: si mcp add <name> --url <url>")
            return 0
        for row in rows:
            state = "connected" if row["ok"] else "offline"
            names = ", ".join(row["tools"]) or "none"
            print(f"{row['id']}  {row['transport']}  {state}  {names}")
        return 0
    if argv[0] == "remove" and len(argv) >= 2:
        result = remove_server(argv[1])
        print("removed" if result.get("ok") else result.get("error"))
        return 0 if result.get("ok") else 1
    if argv[0] == "add" and len(argv) >= 4 and argv[2] in {"--url", "--command"}:
        transport = "http" if argv[2] == "--url" else "stdio"
        result = add_server(argv[1], transport, " ".join(argv[3:]))
        if not result.get("ok"):
            print(result["error"], file=sys.stderr)
            return 1
        server = result["server"]
        print(f"connected {server['id']} ({server['transport']}): {', '.join(server['tools'])}")
        return 0
    print("si mcp list")
    print("si mcp add <name> --url <url>")
    print("si mcp add <name> --command <command>")
    print("si mcp remove <name>")
    return 1


def main(argv: list[str]) -> int:
    yes = "--yes" in argv
    mode = None
    cleaned = []
    skip = False
    for arg in argv:
        if skip:
            mode = arg
            skip = False
            continue
        if arg == "--yes":
            continue
        if arg == "--mode":
            skip = True
            continue
        cleaned.append(arg)
    argv = cleaned
    if not argv or argv[0] in {"-h", "--help"}:
        print("si mode <auto|semi|man>")
        print("si mcp add <name> --url <url>")
        print("si <sentence | pcb ... | cad ...>")
        return 0
    if argv[0] == "mode" and len(argv) == 2:
        result = set_mode(argv[1])
        print(result["mode"] if result.get("ok") else result["error"])
        return 0 if result.get("ok") else 1
    if argv[0] == "mcp":
        return mcp_command(argv[1:])
    body = designer_turn(" ".join(argv), approved=yes, mode=mode)
    if body.get("needsApproval"):
        if yes:
            body = decide(str(body["proposalId"]), "allow")
        else:
            body = approve_interactive(body)
            if body.get("needsApproval"):
                return 2
    print_turn(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

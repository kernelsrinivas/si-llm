//! Production CLI. No Python at runtime.
//!
//!   si mcp add pcb --url http://127.0.0.1:8766/mcp
//!   si mode auto
//!   si --yes "place a resistor r1 at 10 12"

use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;

const READONLY: &[&str] = &[
    "pcb_drc", "pcb_status", "pcb_find", "cad_mass", "cad_status", "sch_erc", "sim_dc", "sim_tran",
    "view_3d", "fab_stack", "asm_bom", "chip_check", "industry_check", "cover_all", "impedance",
    "dfm", "via", "ipc_check", "desk", "feature_audit",
];

#[derive(Clone)]
struct Server {
    transport: String,
    target: String,
}

struct Config {
    servers: BTreeMap<String, Server>,
    always: Vec<String>,
    mode: String,
}

fn main() {
    let code = match run(env::args().skip(1).collect()) {
        Ok(code) => code,
        Err(err) => {
            eprintln!("{err}");
            1
        }
    };
    std::process::exit(code);
}

fn run(args: Vec<String>) -> Result<i32, String> {
    let mut yes = false;
    let mut mode_flag: Option<String> = None;
    let mut cleaned = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--yes" => yes = true,
            "--mode" => {
                i += 1;
                mode_flag = Some(args.get(i).cloned().ok_or_else(|| "mode needs auto, semi, or man".to_string())?);
            }
            _ => cleaned.push(args[i].clone()),
        }
        i += 1;
    }
    if cleaned.is_empty() || cleaned[0] == "-h" || cleaned[0] == "--help" {
        print_help();
        return Ok(0);
    }
    if cleaned[0] == "mode" && cleaned.len() == 2 {
        let raw = model_post("/mode", &format!("{{\"mode\":\"{}\"}}", escape(&cleaned[1])))?;
        if raw.contains("\"ok\": false") || raw.contains("\"ok\":false") {
            let err = json_string(&raw, "error");
            return Err(if err.is_empty() { "Mode is auto, semi, or man.".into() } else { err });
        }
        println!("{}", json_string(&raw, "mode"));
        return Ok(0);
    }
    if cleaned[0] == "mcp" {
        return mcp(&cleaned[1..]);
    }
    if cleaned[0] == "agents" {
        return print_roster();
    }
    if cleaned[0] == "agent" {
        if cleaned.len() < 2 {
            return print_roster();
        }
        let text = cleaned[2..].join(" ");
        return crew_call("/agent", &format!("{{\"agent\":\"{}\",\"text\":\"{}\",\"approved\":{}{}}}", escape(&cleaned[1]), escape(&text), if yes { "true" } else { "false" }, mode_json(mode_flag.as_deref())), yes);
    }
    if cleaned[0] == "crew" {
        let text = cleaned[1..].join(" ");
        return crew_call("/crew", &format!("{{\"text\":\"{}\",\"approved\":{}{}}}", escape(&text), if yes { "true" } else { "false" }, mode_json(mode_flag.as_deref())), yes);
    }
    let text = cleaned.join(" ");
    let raw = model_ask(&text, yes, mode_flag.as_deref())?;
    if needs_approval(&raw) && !yes {
        print_model(&raw)?;
        if !atty() {
            println!("Not sent. Pass --yes to allow once.");
            return Ok(2);
        }
        print!("Allow? [y]es / [a]lways / [n]o: ");
        let _ = std::io::stdout().flush();
        let mut line = String::new();
        std::io::stdin().read_line(&mut line).map_err(|e| e.to_string())?;
        let decision = match line.trim().to_ascii_lowercase().as_str() {
            "y" | "yes" => "allow",
            "a" | "always" => "always",
            _ => {
                println!("Not sent.");
                return Ok(2);
            }
        };
        let proposal = json_string(&raw, "proposalId");
        let approved = model_post("/approve", &format!("{{\"proposalId\":\"{proposal}\",\"decision\":\"{decision}\"}}"))?;
        print_model(&approved)?;
        return Ok(0);
    }
    print_model(&raw)?;
    Ok(0)
}

fn model_url() -> String {
    std::env::var("SI_URL").unwrap_or_else(|_| "http://127.0.0.1:8765".into())
}

fn model_post(path: &str, body: &str) -> Result<String, String> {
    http_exchange("POST", &format!("{}{path}", model_url()), body)
}

fn model_get(path: &str) -> Result<String, String> {
    http_exchange("GET", &format!("{}{path}", model_url()), "")
}

fn model_ask(text: &str, yes: bool, mode: Option<&str>) -> Result<String, String> {
    let approved = if yes { "true" } else { "false" };
    let mode_json = match mode {
        Some(mode) if !mode.is_empty() => format!(",\"mode\":\"{}\"", escape(mode)),
        _ => String::new(),
    };
    model_post("/cli", &format!("{{\"text\":\"{}\",\"approved\":{approved}{mode_json}}}", escape(text)))
}

fn json_string(raw: &str, key: &str) -> String {
    string_field(raw, key).unwrap_or_default()
}

fn needs_approval(raw: &str) -> bool {
    raw.contains("\"needsApproval\": true") || raw.contains("\"needsApproval\":true")
}

fn print_model(raw: &str) -> Result<(), String> {
    if raw.contains("\"ok\": false") || raw.contains("\"ok\":false") {
        return Err(json_string(raw, "error"));
    }
    let reply = json_string(raw, "reply");
    if reply.is_empty() {
        return Err(raw.to_string());
    }
    println!("{reply}");
    if let Some(commands_at) = raw.find("\"commands\"") {
        let slice = &raw[commands_at..];
        if let Some(cmd) = string_field(slice, "commands").or_else(|| {
            let start = slice.find('[').unwrap_or(0);
            string_field(&slice[start..], "")
        }) {
            if !cmd.is_empty() && cmd != "commands" {
                let runtime = json_string(raw, "runtime");
                println!("[{}] {cmd}", if runtime.is_empty() { "model" } else { &runtime });
            }
        }
    }
    Ok(())
}

fn mode_json(mode: Option<&str>) -> String {
    match mode {
        Some(mode) if !mode.is_empty() => format!(",\"mode\":\"{}\"", escape(mode)),
        _ => String::new(),
    }
}

fn print_roster() -> Result<i32, String> {
    let raw = model_get("/agents")?;
    if raw.contains("\"ok\": false") || raw.contains("\"ok\":false") {
        return Err(json_string(&raw, "error"));
    }
    let mut rest = raw.as_str();
    let mut any = false;
    while let Some(pos) = rest.find("\"id\"") {
        let id = json_string(&rest[pos..], "id");
        let role = json_string(&rest[pos..], "role");
        let does = json_string(&rest[pos..], "does");
        if id.is_empty() {
            break;
        }
        println!("{id}  {role}  {does}");
        any = true;
        rest = &rest[pos + 4..];
    }
    if !any {
        println!("No agents.");
    }
    Ok(0)
}

fn crew_call(path: &str, body: &str, yes: bool) -> Result<i32, String> {
    let mut raw = model_post(path, body)?;
    let rest = raw.contains("\"crewRest\": true") || raw.contains("\"crewRest\":true");
    let needed = needs_approval(&raw);
    if needed && !yes {
        print_model(&raw)?;
        if !atty() {
            println!("Not sent. Pass --yes to allow once.");
            return Ok(2);
        }
        print!("Allow? [y]es / [a]lways / [n]o: ");
        let _ = std::io::stdout().flush();
        let mut line = String::new();
        std::io::stdin().read_line(&mut line).map_err(|e| e.to_string())?;
        let decision = match line.trim().to_ascii_lowercase().as_str() {
            "y" | "yes" => "allow",
            "a" | "always" => "always",
            _ => {
                println!("Not sent.");
                return Ok(2);
            }
        };
        let proposal = json_string(&raw, "proposalId");
        raw = model_post("/approve", &format!("{{\"proposalId\":\"{proposal}\",\"decision\":\"{decision}\"}}"))?;
        print_model(&raw)?;
        if rest {
            raw = model_post("/crew", "{\"resume\":true,\"approved\":true}")?;
            print_model(&raw)?;
        }
        return Ok(0);
    }
    print_model(&raw)?;
    Ok(0)
}

fn print_help() {
    println!("si mode <auto|semi|man>");
    println!("si agents");
    println!("si agent <name> \"task\"");
    println!("si crew \"finish the board\"");
    println!("si mcp add <name> --url <url>");
    println!("si mcp add <name> --command <command>");
    println!("si mcp list");
    println!("si mcp remove <name>");
    println!("si --mode <auto|semi|man> --yes \"place a resistor r1 at 10 12\"");
    println!("The CLI is the model client. The server at {} runs the trained model.", model_url());
}

fn gated(mode: &str, tool: &str, key: &str, always: &[String]) -> bool {
    if mode == "auto" {
        return false;
    }
    if mode == "semi" && READONLY.contains(&tool) {
        return false;
    }
    !always.iter().any(|item| item == key)
}

fn atty() -> bool {
    #[cfg(unix)]
    {
        std::io::IsTerminal::is_terminal(&std::io::stdin())
    }
    #[cfg(not(unix))]
    {
        std::io::IsTerminal::is_terminal(&std::io::stdin())
    }
}

fn mcp(argv: &[String]) -> Result<i32, String> {
    if argv.is_empty() || argv[0] == "list" || argv[0] == "ls" {
        let raw = model_get("/health")?;
        let Some(start) = raw.find("\"servers\"") else {
            println!("No MCP connections. Add one with: si mcp add <name> --url <url>");
            return Ok(0);
        };
        let mut cursor = start;
        let mut any = false;
        while let Some(pos) = raw[cursor..].find("\"id\"") {
            let at = cursor + pos;
            let id = json_string(&raw[at..], "id");
            if id.is_empty() {
                break;
            }
            let transport = json_string(&raw[at..], "transport");
            let window = &raw[at..raw.len().min(at + 500)];
            let ok = window.contains("\"ok\": true") || window.contains("\"ok\":true");
            println!("{id}  {transport}  {}", if ok { "connected" } else { "offline" });
            any = true;
            cursor = at + 4;
        }
        if !any {
            println!("No MCP connections. Add one with: si mcp add <name> --url <url>");
        }
        return Ok(0);
    }
    if argv[0] == "remove" && argv.len() >= 2 {
        let raw = model_post("/mcp/remove", &format!("{{\"name\":\"{}\"}}", escape(&argv[1])))?;
        if raw.contains("\"ok\": false") || raw.contains("\"ok\":false") {
            return Err(json_string(&raw, "error"));
        }
        println!("removed");
        return Ok(0);
    }
    if argv[0] == "add" && argv.len() >= 4 && (argv[2] == "--url" || argv[2] == "--command") {
        let transport = if argv[2] == "--url" { "http" } else { "stdio" };
        let target = argv[3..].join(" ");
        let raw = model_post(
            "/mcp/add",
            &format!("{{\"name\":\"{}\",\"transport\":\"{transport}\",\"target\":\"{}\"}}", escape(&argv[1]), escape(&target)),
        )?;
        if raw.contains("\"ok\": false") || raw.contains("\"ok\":false") {
            let err = json_string(&raw, "error");
            return Err(if err.is_empty() { "Could not connect.".into() } else { err });
        }
        println!("connected {} ({transport})", argv[1]);
        return Ok(0);
    }
    println!("si mcp list");
    println!("si mcp add <name> --url <url>");
    println!("si mcp add <name> --command <command>");
    println!("si mcp remove <name>");
    Ok(1)
}

fn parse_sentence(text: &str) -> Result<(String, String, Vec<(String, String)>), String> {
    let words: Vec<String> = text
        .split(|c: char| !c.is_ascii_alphanumeric() && c != '.')
        .filter(|w| !w.is_empty())
        .map(|w| w.to_ascii_lowercase())
        .collect();
    if words.is_empty() {
        return Err("Say a place, connect, move, or status command.".into());
    }
    let head = words[0].as_str();
    if matches!(head, "place" | "add" | "put" | "mount") {
        let rest = skip_fillers(&words[1..]);
        if rest.len() < 4 {
            return Err("place <part> <ref> at <x> <y>".into());
        }
        let pkg = map_pkg(&rest[0]);
        let mut idx = 1;
        if rest.get(idx).map(|s| s.as_str()) == Some("as") {
            idx += 1;
        }
        let r = rest.get(idx).ok_or("missing ref")?.clone();
        idx += 1;
        if rest.get(idx).map(|s| s.as_str()) == Some("at") {
            idx += 1;
        }
        let x = rest.get(idx).ok_or("missing x")?.clone();
        let y = rest.get(idx + 1).ok_or("missing y")?.clone();
        return Ok(("pcb".into(), "pcb_add".into(), vec![("ref".into(), r), ("pkg".into(), pkg), ("x".into(), x), ("y".into(), y)]));
    }
    if matches!(head, "connect" | "tie" | "wire") {
        let rest = &words[1..];
        if rest.len() < 4 {
            return Err("connect <net> from <ref> to <ref>".into());
        }
        let net = rest[0].clone();
        let mut idx = 1;
        if matches!(rest.get(idx).map(|s| s.as_str()), Some("from" | "between")) {
            idx += 1;
        }
        let a = rest.get(idx).ok_or("missing ref")?.clone();
        idx += 1;
        if matches!(rest.get(idx).map(|s| s.as_str()), Some("to" | "and")) {
            idx += 1;
        }
        let b = rest.get(idx).ok_or("missing ref")?.clone();
        return Ok(("pcb".into(), "pcb_net".into(), vec![("name".into(), net), ("a".into(), a), ("b".into(), b)]));
    }
    if matches!(head, "delete" | "remove") {
        let r = words.get(1).ok_or("delete <ref>")?.clone();
        return Ok(("pcb".into(), "pcb_delete".into(), vec![("ref".into(), r)]));
    }
    if head == "move" {
        let r = words.get(1).ok_or("move <ref> to <x> <y>")?.clone();
        let nums: Vec<&String> = words.iter().filter(|w| w.chars().all(|c| c.is_ascii_digit() || c == '.')).collect();
        if nums.len() < 2 {
            return Err("move <ref> to <x> <y>".into());
        }
        return Ok(("pcb".into(), "pcb_move".into(), vec![("ref".into(), r), ("x".into(), nums[0].clone()), ("y".into(), nums[1].clone())]));
    }
    if head == "rotate" {
        let r = words.get(1).ok_or("rotate <ref> <degrees>")?.clone();
        let angle = words.iter().rev().find(|w| w.chars().all(|c| c.is_ascii_digit())).cloned().unwrap_or_else(|| "90".into());
        return Ok(("pcb".into(), "pcb_rotate".into(), vec![("ref".into(), r), ("angle".into(), angle)]));
    }
    if head == "flip" || head == "mirror" {
        let r = words.get(1).cloned().unwrap_or_else(|| "u1".into());
        return Ok(("pcb".into(), "pcb_flip".into(), vec![("ref".into(), r)]));
    }
    if head == "find" {
        let r = words.get(1).ok_or("find <ref>")?.clone();
        return Ok(("pcb".into(), "pcb_find".into(), vec![("ref".into(), r)]));
    }
    if head == "pcb" && words.get(1).map(|s| s.as_str()) == Some("status") || words == ["status"] || text.eq_ignore_ascii_case("show me the board") {
        return Ok(("pcb".into(), "pcb_status".into(), vec![]));
    }
    if words.iter().any(|w| w == "drc") || text.eq_ignore_ascii_case("check the board") {
        return Ok(("pcb".into(), "pcb_drc".into(), vec![]));
    }
    if words.iter().any(|w| w == "gerber" || w == "gerbers") {
        return Ok(("pcb".into(), "fab_gerber".into(), vec![]));
    }
    if head == "bom" || words.iter().any(|w| w == "bom") {
        return Ok(("pcb".into(), "asm_bom".into(), vec![]));
    }
    if head == "outline" {
        let nums: Vec<&String> = words.iter().filter(|w| w.chars().all(|c| c.is_ascii_digit() || c == '.')).collect();
        if nums.len() < 2 {
            return Err("outline <length> <width>".into());
        }
        return Ok(("pcb".into(), "set_outline".into(), vec![("length".into(), nums[0].clone()), ("width".into(), nums[1].clone())]));
    }
    if head == "cad" && words.get(1).map(|s| s.as_str()) == Some("status") {
        return Ok(("cad".into(), "cad_status".into(), vec![]));
    }
    Err("The native client takes a direct command: place, connect, move, rotate, delete, status, drc, gerber, bom, outline. Board-name catalogs stay in the trainer, not in this binary.".into())
}

fn skip_fillers(words: &[String]) -> Vec<String> {
    words.iter().filter(|w| !matches!(w.as_str(), "a" | "an" | "the")).cloned().collect()
}

fn map_pkg(word: &str) -> String {
    match word {
        "resistor" => "res".into(),
        "capacitor" => "cap".into(),
        "inductor" | "coil" => "ind".into(),
        "transistor" => "bjt".into(),
        "mosfet" => "fet".into(),
        "connector" => "conn".into(),
        other => other.to_string(),
    }
}

fn config_path() -> Result<PathBuf, String> {
    if let Ok(path) = env::var("SI_CONFIG") {
        return Ok(PathBuf::from(path));
    }
    let home = env::var("HOME").or_else(|_| env::var("USERPROFILE")).map_err(|_| "HOME is not set".to_string())?;
    let dir = if cfg!(target_os = "windows") {
        PathBuf::from(env::var("APPDATA").unwrap_or(home)).join("si-llm")
    } else if cfg!(target_os = "macos") {
        PathBuf::from(home).join("Library").join("Application Support").join("si-llm")
    } else {
        let base = env::var("XDG_CONFIG_HOME").unwrap_or_else(|_| format!("{home}/.config"));
        PathBuf::from(base).join("si-llm")
    };
    Ok(dir.join("mcp.json"))
}

fn load() -> Result<Config, String> {
    let path = config_path()?;
    if !path.exists() {
        return Ok(Config { servers: BTreeMap::new(), always: Vec::new(), mode: "man".into() });
    }
    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let value = parse_json(&raw)?;
    let mut cfg = Config { servers: BTreeMap::new(), always: Vec::new(), mode: "man".into() };
    if let Json::Object(map) = value {
        if let Some(Json::String(mode)) = map.get("mode") {
            if matches!(mode.as_str(), "auto" | "semi" | "man") {
                cfg.mode = mode.clone();
            }
        }
        if let Some(Json::Array(items)) = map.get("alwaysAllow") {
            for item in items {
                if let Json::String(name) = item {
                    cfg.always.push(name.clone());
                }
            }
        }
        if let Some(Json::Object(servers)) = map.get("mcpServers") {
            for (id, spec) in servers {
                if let Json::Object(fields) = spec {
                    let transport = match fields.get("transport") {
                        Some(Json::String(v)) => v.clone(),
                        _ => "http".into(),
                    };
                    let target = match fields.get("target") {
                        Some(Json::String(v)) => v.clone(),
                        _ => String::new(),
                    };
                    cfg.servers.insert(id.clone(), Server { transport, target });
                }
            }
        }
    }
    Ok(cfg)
}

fn save(cfg: &Config) -> Result<(), String> {
    let path = config_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let mut servers = String::from("{");
    for (i, (id, server)) in cfg.servers.iter().enumerate() {
        if i > 0 {
            servers.push(',');
        }
        servers.push_str(&format!(
            "\n    \"{}\": {{\"transport\": \"{}\", \"target\": \"{}\"}}",
            escape(id),
            escape(&server.transport),
            escape(&server.target)
        ));
    }
    if !cfg.servers.is_empty() {
        servers.push_str("\n  ");
    }
    servers.push('}');
    let always = cfg.always.iter().map(|item| format!("\"{}\"", escape(item))).collect::<Vec<_>>().join(", ");
    let body = format!(
        "{{\n  \"mcpServers\": {servers},\n  \"alwaysAllow\": [{always}],\n  \"mode\": \"{}\"\n}}\n",
        escape(&cfg.mode)
    );
    fs::write(path, body).map_err(|e| e.to_string())
}

fn probe(server: &Server) -> Result<Vec<String>, String> {
    let init = rpc(server, "initialize", "{}")?;
    if init.contains("\"error\"") && !init.contains("\"result\"") {
        return Err(init);
    }
    let listed = rpc(server, "tools/list", "{}")?;
    Ok(tool_names(&listed))
}

fn call(server: &Server, tool: &str, args: &[(String, String)]) -> Result<String, String> {
    let mut arguments = String::from("{");
    for (i, (key, value)) in args.iter().enumerate() {
        if i > 0 {
            arguments.push(',');
        }
        let encoded = if value.chars().all(|c| c.is_ascii_digit() || c == '.') && value.contains('.') || value.chars().all(|c| c.is_ascii_digit()) {
            value.clone()
        } else if value.chars().all(|c| c.is_ascii_digit() || c == '.') && !value.is_empty() {
            value.clone()
        } else {
            format!("\"{}\"", escape(value))
        };
        arguments.push_str(&format!("\"{}\": {encoded}", escape(key)));
    }
    arguments.push('}');
    let params = format!("{{\"name\": \"{}\", \"arguments\": {arguments}}}", escape(tool));
    let raw = rpc(server, "tools/call", &params)?;
    if let Some(text) = string_field(&raw, "text") {
        return Ok(text);
    }
    if raw.contains("\"isError\": true") || raw.contains("\"isError\":true") {
        return Err(raw);
    }
    Ok(raw)
}

fn rpc(server: &Server, method: &str, params: &str) -> Result<String, String> {
    let body = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"{}\",\"params\":{params}}}",
        escape(method)
    );
    if server.transport == "stdio" {
        return stdio_rpc(&server.target, &body);
    }
    http_post(&server.target, &body)
}

fn http_exchange(method: &str, url: &str, body: &str) -> Result<String, String> {
    let rest = url.strip_prefix("http://").ok_or_else(|| "only http:// URLs are supported".to_string())?;
    let (hostport, path) = rest.split_once('/').unwrap_or((rest, ""));
    let path = format!("/{path}");
    let (host, port) = match hostport.split_once(':') {
        Some((host, port)) => (host, port.parse::<u16>().map_err(|_| "bad port".to_string())?),
        None => (hostport, 80u16),
    };
    let mut stream = TcpStream::connect((host, port)).map_err(|_| format!("The model server is not running at {}", model_url()))?;
    stream.set_read_timeout(Some(Duration::from_secs(60))).ok();
    stream.set_write_timeout(Some(Duration::from_secs(30))).ok();
    let token = std::env::var("SI_TOKEN").unwrap_or_default();
    let auth = if url.starts_with(&model_url()) && !token.is_empty() {
        format!("\r\nAuthorization: Bearer {token}")
    } else {
        String::new()
    };
    let req = format!(
        "{method} {path} HTTP/1.0\r\nHost: {host}:{port}\r\nContent-Type: application/json\r\nContent-Length: {}{auth}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(req.as_bytes()).map_err(|e| e.to_string())?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&raw);
    let body = text.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or(&text);
    Ok(body.trim().to_string())
}

fn http_post(url: &str, body: &str) -> Result<String, String> {
    http_exchange("POST", url, body)
}

fn stdio_rpc(command: &str, body: &str) -> Result<String, String> {
    let mut child = if cfg!(target_os = "windows") {
        Command::new("cmd").args(["/C", command]).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?
    } else {
        Command::new("sh").args(["-c", command]).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().map_err(|e| e.to_string())?
    };
    {
        let stdin = child.stdin.as_mut().ok_or("no stdin")?;
        stdin.write_all(body.as_bytes()).map_err(|e| e.to_string())?;
        stdin.write_all(b"\n").map_err(|e| e.to_string())?;
    }
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&output.stdout);
    Ok(text.lines().next().unwrap_or("").to_string())
}

fn tool_names(raw: &str) -> Vec<String> {
    let mut names = Vec::new();
    let mut rest = raw;
    while let Some(pos) = rest.find("\"name\"") {
        rest = &rest[pos + 6..];
        if let Some(text) = string_field(&format!("\"name\"{rest}"), "name") {
            if !names.contains(&text) {
                names.push(text);
            }
        }
        if rest.len() > 8 {
            rest = &rest[1..];
        } else {
            break;
        }
    }
    names
}

fn string_field(raw: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let mut rest = raw;
    while let Some(pos) = rest.find(&needle) {
        let after = &rest[pos + needle.len()..];
        let trimmed = after.trim_start();
        if let Some(value) = trimmed.strip_prefix(':') {
            let trimmed = value.trim_start();
            if trimmed.starts_with('"') {
                return parse_string(&mut trimmed.chars().peekable()).ok();
            }
        }
        rest = &rest[pos + needle.len()..];
    }
    None
}

fn escape(text: &str) -> String {
    text.replace('\\', "\\\\").replace('"', "\\\"")
}

#[derive(Clone)]
enum Json {
    Object(BTreeMap<String, Json>),
    Array(Vec<Json>),
    String(String),
    Other,
}

fn parse_json(raw: &str) -> Result<Json, String> {
    let mut chars = raw.chars().peekable();
    parse_value(&mut chars)
}

fn parse_value(chars: &mut std::iter::Peekable<std::str::Chars>) -> Result<Json, String> {
    skip(chars);
    match chars.peek().copied() {
        Some('{') => {
            chars.next();
            let mut map = BTreeMap::new();
            loop {
                skip(chars);
                if chars.peek() == Some(&'}') {
                    chars.next();
                    break;
                }
                let key = match parse_value(chars)? {
                    Json::String(s) => s,
                    _ => return Err("bad json key".into()),
                };
                skip(chars);
                if chars.next() != Some(':') {
                    return Err("bad json".into());
                }
                map.insert(key, parse_value(chars)?);
                skip(chars);
                if chars.peek() == Some(&',') {
                    chars.next();
                    continue;
                }
                if chars.peek() == Some(&'}') {
                    chars.next();
                    break;
                }
            }
            Ok(Json::Object(map))
        }
        Some('[') => {
            chars.next();
            let mut items = Vec::new();
            loop {
                skip(chars);
                if chars.peek() == Some(&']') {
                    chars.next();
                    break;
                }
                items.push(parse_value(chars)?);
                skip(chars);
                if chars.peek() == Some(&',') {
                    chars.next();
                    continue;
                }
                if chars.peek() == Some(&']') {
                    chars.next();
                    break;
                }
            }
            Ok(Json::Array(items))
        }
        Some('"') => Ok(Json::String(parse_string(chars)?)),
        Some(_) => {
            while let Some(c) = chars.peek() {
                if ",}]".contains(*c) || c.is_whitespace() {
                    break;
                }
                chars.next();
            }
            Ok(Json::Other)
        }
        None => Err("empty json".into()),
    }
}

fn parse_string(chars: &mut std::iter::Peekable<std::str::Chars>) -> Result<String, String> {
    if chars.next() != Some('"') {
        return Err("bad string".into());
    }
    let mut out = String::new();
    while let Some(c) = chars.next() {
        match c {
            '\\' => match chars.next() {
                Some('n') => out.push('\n'),
                Some('t') => out.push('\t'),
                Some('r') => out.push('\r'),
                Some(n) => out.push(n),
                None => {}
            },
            '"' => return Ok(out),
            _ => out.push(c),
        }
    }
    Err("unterminated string".into())
}

fn skip(chars: &mut std::iter::Peekable<std::str::Chars>) {
    while matches!(chars.peek(), Some(c) if c.is_whitespace()) {
        chars.next();
    }
}

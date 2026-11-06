// Xcode command-line tool. C++17, no Python.
// Open native/xcode/si.xcodeproj on a Mac and run the "si" scheme.
// Linux check: g++ -std=c++17 -O2 -o si native/xcode/si/main.cpp

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace {

const char *kReadonly[] = {
    "pcb_drc", "pcb_status", "pcb_find", "cad_mass", "cad_status", "sch_erc", "sim_dc", "sim_tran",
    "view_3d", "fab_stack", "asm_bom", "chip_check", "industry_check", "cover_all", "impedance", "dfm",
    "via", "ipc_check", "desk", "feature_audit", nullptr};

struct Server {
  std::string transport;
  std::string target;
};

struct Config {
  std::map<std::string, Server> servers;
  std::vector<std::string> always;
  std::string mode = "man";
};

std::string lower(std::string text) {
  for (char &c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return text;
}

std::string escape(const std::string &text) {
  std::string out;
  for (char c : text) {
    if (c == '\\' || c == '"') out.push_back('\\');
    out.push_back(c);
  }
  return out;
}

bool is_readonly(const std::string &tool) {
  for (int i = 0; kReadonly[i]; ++i)
    if (tool == kReadonly[i]) return true;
  return false;
}

std::string home_dir() {
  if (const char *home = std::getenv("HOME")) return home;
  if (const char *home = std::getenv("USERPROFILE")) return home;
  return ".";
}

std::string config_path() {
  if (const char *over = std::getenv("SI_CONFIG")) return over;
#if defined(_WIN32)
  const char *appdata = std::getenv("APPDATA");
  return std::string(appdata ? appdata : home_dir()) + "\\si-llm\\mcp.json";
#elif defined(__APPLE__)
  return home_dir() + "/Library/Application Support/si-llm/mcp.json";
#else
  if (const char *xdg = std::getenv("XDG_CONFIG_HOME")) return std::string(xdg) + "/si-llm/mcp.json";
  return home_dir() + "/.config/si-llm/mcp.json";
#endif
}

void ensure_parent(const std::string &path) {
  auto slash = path.find_last_of("/\\");
  if (slash == std::string::npos) return;
  std::string dir = path.substr(0, slash);
#if defined(_WIN32)
  std::string cmd = "mkdir \"" + dir + "\" 2>nul";
#else
  std::string cmd = "mkdir -p \"" + dir + "\"";
#endif
  std::system(cmd.c_str());
}

std::string read_file(const std::string &path) {
  std::ifstream in(path);
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

Config load() {
  Config cfg;
  std::string raw = read_file(config_path());
  if (raw.empty()) return cfg;
  auto mode = raw.find("\"mode\"");
  if (mode != std::string::npos) {
    auto q1 = raw.find('"', raw.find(':', mode) + 1);
    auto q2 = raw.find('"', q1 + 1);
    if (q1 != std::string::npos && q2 != std::string::npos) {
      std::string value = raw.substr(q1 + 1, q2 - q1 - 1);
      if (value == "auto" || value == "semi" || value == "man") cfg.mode = value;
    }
  }
  auto allow = raw.find("\"alwaysAllow\"");
  if (allow != std::string::npos) {
    auto end = raw.find(']', allow);
    std::string slice = raw.substr(allow, end - allow);
    std::size_t at = 0;
    while ((at = slice.find('"', at)) != std::string::npos) {
      auto stop = slice.find('"', at + 1);
      if (stop == std::string::npos) break;
      std::string item = slice.substr(at + 1, stop - at - 1);
      if (item != "alwaysAllow") cfg.always.push_back(item);
      at = stop + 1;
    }
  }
  std::size_t at = 0;
  while ((at = raw.find("\"transport\"", at)) != std::string::npos) {
    auto id_end = raw.rfind('"', at - 1);
    auto id_start = raw.rfind('"', id_end - 1);
    if (id_start == std::string::npos) break;
    std::string id = raw.substr(id_start + 1, id_end - id_start - 1);
    auto t1 = raw.find('"', raw.find(':', at) + 1);
    auto t2 = raw.find('"', t1 + 1);
    auto target_key = raw.find("\"target\"", at);
    auto g1 = raw.find('"', raw.find(':', target_key) + 1);
    auto g2 = raw.find('"', g1 + 1);
    Server server;
    server.transport = raw.substr(t1 + 1, t2 - t1 - 1);
    server.target = raw.substr(g1 + 1, g2 - g1 - 1);
    cfg.servers[id] = server;
    at = g2 + 1;
  }
  return cfg;
}

void save(const Config &cfg) {
  std::ostringstream out;
  out << "{\n  \"mcpServers\": {";
  bool first = true;
  for (const auto &item : cfg.servers) {
    if (!first) out << ",";
    first = false;
    out << "\n    \"" << escape(item.first) << "\": {\"transport\": \"" << escape(item.second.transport)
        << "\", \"target\": \"" << escape(item.second.target) << "\"}";
  }
  if (!cfg.servers.empty()) out << "\n  ";
  out << "},\n  \"alwaysAllow\": [";
  for (std::size_t i = 0; i < cfg.always.size(); ++i) {
    if (i) out << ", ";
    out << "\"" << escape(cfg.always[i]) << "\"";
  }
  out << "],\n  \"mode\": \"" << escape(cfg.mode) << "\"\n}\n";
  auto path = config_path();
  ensure_parent(path);
  std::ofstream file(path);
  file << out.str();
}

std::string http_post(const std::string &url, const std::string &body) {
  if (url.compare(0, 7, "http://") != 0) throw std::runtime_error("only http:// MCP URLs are supported");
  std::string rest = url.substr(7);
  auto slash = rest.find('/');
  std::string hostport = slash == std::string::npos ? rest : rest.substr(0, slash);
  std::string path = slash == std::string::npos ? "/" : rest.substr(slash);
  std::string host = hostport;
  int port = 80;
  auto colon = hostport.find(':');
  if (colon != std::string::npos) {
    host = hostport.substr(0, colon);
    port = std::atoi(hostport.substr(colon + 1).c_str());
  }
#if defined(_WIN32)
  WSADATA data;
  WSAStartup(MAKEWORD(2, 2), &data);
  SOCKET fd = socket(AF_INET, SOCK_STREAM, 0);
#else
  int fd = socket(AF_INET, SOCK_STREAM, 0);
#endif
  if (fd < 0) throw std::runtime_error("socket failed");
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo *res = nullptr;
  if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &res) != 0) throw std::runtime_error("dns failed");
  if (connect(fd, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
    freeaddrinfo(res);
    throw std::runtime_error(host + " refused the connection");
  }
  freeaddrinfo(res);
  std::ostringstream req;
  req << "POST " << path << " HTTP/1.0\r\nHost: " << host << ":" << port
      << "\r\nContent-Type: application/json\r\nContent-Length: " << body.size() << "\r\nConnection: close\r\n\r\n"
      << body;
  std::string bytes = req.str();
  send(fd, bytes.data(), static_cast<int>(bytes.size()), 0);
  std::string raw;
  char buf[4096];
  int n = 0;
  while ((n = static_cast<int>(recv(fd, buf, sizeof buf, 0))) > 0) raw.append(buf, buf + n);
#if defined(_WIN32)
  closesocket(fd);
#else
  close(fd);
#endif
  auto split = raw.find("\r\n\r\n");
  return split == std::string::npos ? raw : raw.substr(split + 4);
}

std::string rpc(const Server &server, const std::string &method, const std::string &params) {
  if (server.transport != "http") throw std::runtime_error("Xcode CLI speaks HTTP MCP. Use --url.");
  std::string body = std::string("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"") + escape(method) + "\",\"params\":" + params + "}";
  return http_post(server.target, body);
}

std::string json_string_after(const std::string &raw, const std::string &key) {
  std::string needle = "\"" + key + "\"";
  std::size_t at = 0;
  while ((at = raw.find(needle, at)) != std::string::npos) {
    std::size_t i = at + needle.size();
    while (i < raw.size() && std::isspace(static_cast<unsigned char>(raw[i]))) ++i;
    if (i < raw.size() && raw[i] == ':') {
      ++i;
      while (i < raw.size() && std::isspace(static_cast<unsigned char>(raw[i]))) ++i;
      if (i < raw.size() && raw[i] == '"') {
        std::string out;
        for (++i; i < raw.size(); ++i) {
          if (raw[i] == '\\') {
            if (i + 1 < raw.size()) out.push_back(raw[++i]);
            continue;
          }
          if (raw[i] == '"') return out;
          out.push_back(raw[i]);
        }
      }
    }
    at += needle.size();
  }
  return "";
}

std::vector<std::string> tool_names(const std::string &raw) {
  std::vector<std::string> names;
  std::size_t at = 0;
  while ((at = raw.find("\"name\"", at)) != std::string::npos) {
    std::string name = json_string_after(raw.substr(at), "name");
    if (!name.empty() && std::find(names.begin(), names.end(), name) == names.end()) names.push_back(name);
    at += 6;
  }
  return names;
}

std::vector<std::string> probe(const Server &server) {
  rpc(server, "initialize", "{}");
  return tool_names(rpc(server, "tools/list", "{}"));
}

std::string call_tool(const Server &server, const std::string &tool, const std::vector<std::pair<std::string, std::string>> &args) {
  std::ostringstream arguments;
  arguments << "{";
  for (std::size_t i = 0; i < args.size(); ++i) {
    if (i) arguments << ",";
    bool number = !args[i].second.empty() &&
                  std::all_of(args[i].second.begin(), args[i].second.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)) || c == '.'; });
    arguments << "\"" << escape(args[i].first) << "\": " << (number ? args[i].second : "\"" + escape(args[i].second) + "\"");
  }
  arguments << "}";
  std::string params = std::string("{\"name\":\"") + escape(tool) + "\",\"arguments\":" + arguments.str() + "}";
  std::string raw = rpc(server, "tools/call", params);
  std::string text = json_string_after(raw, "text");
  return text.empty() ? raw : text;
}

std::vector<std::string> tokens(const std::string &text) {
  std::vector<std::string> out;
  std::string word;
  for (char c : text) {
    if (std::isalnum(static_cast<unsigned char>(c)) || c == '.') {
      word.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    } else if (!word.empty()) {
      out.push_back(word);
      word.clear();
    }
  }
  if (!word.empty()) out.push_back(word);
  return out;
}

std::string pkg_name(const std::string &word) {
  if (word == "resistor") return "res";
  if (word == "capacitor") return "cap";
  if (word == "inductor" || word == "coil") return "ind";
  if (word == "transistor") return "bjt";
  if (word == "mosfet") return "fet";
  if (word == "connector") return "conn";
  return word;
}

struct Command {
  std::string server;
  std::string tool;
  std::vector<std::pair<std::string, std::string>> args;
};

Command parse_sentence(const std::string &text) {
  auto words = tokens(text);
  if (words.empty()) throw std::runtime_error("Say a place, connect, move, or status command.");
  auto head = words[0];
  auto numberish = [](const std::string &w) {
    return !w.empty() && std::all_of(w.begin(), w.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)) || c == '.'; });
  };
  if (head == "place" || head == "add" || head == "put" || head == "mount") {
    std::vector<std::string> rest;
    for (std::size_t i = 1; i < words.size(); ++i)
      if (words[i] != "a" && words[i] != "an" && words[i] != "the") rest.push_back(words[i]);
    if (rest.size() < 4) throw std::runtime_error("place <part> <ref> at <x> <y>");
    std::size_t idx = 1;
    if (rest[idx] == "as") ++idx;
    std::string ref = rest.at(idx++);
    if (idx < rest.size() && rest[idx] == "at") ++idx;
    Command cmd{"pcb", "pcb_add", {{"ref", ref}, {"pkg", pkg_name(rest[0])}, {"x", rest.at(idx)}, {"y", rest.at(idx + 1)}}};
    return cmd;
  }
  if (head == "connect" || head == "tie" || head == "wire") {
    if (words.size() < 5) throw std::runtime_error("connect <net> from <ref> to <ref>");
    std::size_t idx = 2;
    if (words[idx] == "from" || words[idx] == "between") ++idx;
    std::string a = words.at(idx++);
    if (idx < words.size() && (words[idx] == "to" || words[idx] == "and")) ++idx;
    return {"pcb", "pcb_net", {{"name", words[1]}, {"a", a}, {"b", words.at(idx)}}};
  }
  if (head == "delete" || head == "remove") return {"pcb", "pcb_delete", {{"ref", words.at(1)}}};
  if (head == "move") {
    std::vector<std::string> nums;
    for (const auto &w : words)
      if (numberish(w)) nums.push_back(w);
    if (nums.size() < 2) throw std::runtime_error("move <ref> to <x> <y>");
    return {"pcb", "pcb_move", {{"ref", words.at(1)}, {"x", nums[0]}, {"y", nums[1]}}};
  }
  if (head == "rotate") {
    std::string angle = "90";
    for (auto it = words.rbegin(); it != words.rend(); ++it)
      if (numberish(*it)) {
        angle = *it;
        break;
      }
    return {"pcb", "pcb_rotate", {{"ref", words.at(1)}, {"angle", angle}}};
  }
  if (head == "flip" || head == "mirror") return {"pcb", "pcb_flip", {{"ref", words.size() > 1 ? words[1] : "u1"}}};
  if (head == "find") return {"pcb", "pcb_find", {{"ref", words.at(1)}}};
  if ((head == "pcb" && words.size() > 1 && words[1] == "status") || (words.size() == 1 && head == "status") || lower(text) == "show me the board")
    return {"pcb", "pcb_status", {}};
  if (std::find(words.begin(), words.end(), "drc") != words.end() || lower(text) == "check the board") return {"pcb", "pcb_drc", {}};
  if (std::find(words.begin(), words.end(), "gerber") != words.end() || std::find(words.begin(), words.end(), "gerbers") != words.end())
    return {"pcb", "fab_gerber", {}};
  if (std::find(words.begin(), words.end(), "bom") != words.end()) return {"pcb", "asm_bom", {}};
  if (head == "outline") {
    std::vector<std::string> nums;
    for (const auto &w : words)
      if (numberish(w)) nums.push_back(w);
    if (nums.size() < 2) throw std::runtime_error("outline <length> <width>");
    return {"pcb", "set_outline", {{"length", nums[0]}, {"width", nums[1]}}};
  }
  if (head == "cad" && words.size() > 1 && words[1] == "status") return {"cad", "cad_status", {}};
  throw std::runtime_error("The Xcode client takes a direct command: place, connect, move, rotate, delete, status, drc, gerber, bom, outline.");
}

void help() {
  std::cout << "si mode <auto|semi|man>\n"
            << "si mcp add <name> --url <url>\n"
            << "si mcp list\n"
            << "si mcp remove <name>\n"
            << "si --mode <auto|semi|man> --yes \"place a resistor r1 at 10 12\"\n"
            << "Xcode C++ client. The same scheme also builds the Rust binary as si-rust when cargo is installed. Neither runs the PyTorch trainer.\n";
}

bool gated(const std::string &mode, const std::string &tool, const std::string &key, const std::vector<std::string> &always) {
  if (mode == "auto") return false;
  if (mode == "semi" && is_readonly(tool)) return false;
  return std::find(always.begin(), always.end(), key) == always.end();
}

int mcp(const std::vector<std::string> &argv) {
  if (argv.empty() || argv[0] == "list" || argv[0] == "ls") {
    Config cfg = load();
    if (cfg.servers.empty()) {
      std::cout << "No MCP connections. Add one with: si mcp add <name> --url <url>\n";
      return 0;
    }
    for (const auto &item : cfg.servers) {
      try {
        auto names = probe(item.second);
        std::cout << item.first << "  " << item.second.transport << "  connected  ";
        for (std::size_t i = 0; i < names.size(); ++i) {
          if (i) std::cout << ", ";
          std::cout << names[i];
        }
        std::cout << "\n";
      } catch (...) {
        std::cout << item.first << "  " << item.second.transport << "  offline\n";
      }
    }
    return 0;
  }
  if (argv[0] == "remove" && argv.size() >= 2) {
    Config cfg = load();
    if (!cfg.servers.erase(argv[1])) throw std::runtime_error("unknown server " + argv[1]);
    std::string prefix = argv[1] + ".";
    cfg.always.erase(std::remove_if(cfg.always.begin(), cfg.always.end(), [&](const std::string &item) { return item.compare(0, prefix.size(), prefix) == 0; }), cfg.always.end());
    save(cfg);
    std::cout << "removed\n";
    return 0;
  }
  if (argv[0] == "add" && argv.size() >= 4 && argv[2] == "--url") {
    std::string target;
    for (std::size_t i = 3; i < argv.size(); ++i) {
      if (!target.empty()) target.push_back(' ');
      target += argv[i];
    }
    Server server{"http", target};
    auto names = probe(server);
    Config cfg = load();
    cfg.servers[argv[1]] = server;
    save(cfg);
    std::cout << "connected " << argv[1] << " (http): ";
    for (std::size_t i = 0; i < names.size(); ++i) {
      if (i) std::cout << ", ";
      std::cout << names[i];
    }
    std::cout << "\n";
    return 0;
  }
  std::cout << "si mcp list\nsi mcp add <name> --url <url>\nsi mcp remove <name>\n";
  return 1;
}

}  // namespace

int main(int argc, char **argv) {
  try {
    std::vector<std::string> args;
    bool yes = false;
    std::string mode_flag;
    for (int i = 1; i < argc; ++i) {
      std::string arg = argv[i];
      if (arg == "--yes") yes = true;
      else if (arg == "--mode" && i + 1 < argc) mode_flag = argv[++i];
      else args.push_back(arg);
    }
    if (args.empty() || args[0] == "-h" || args[0] == "--help") {
      help();
      return 0;
    }
    if (args[0] == "mode" && args.size() == 2) {
      if (args[1] != "auto" && args[1] != "semi" && args[1] != "man") throw std::runtime_error("Mode is auto, semi, or man.");
      Config cfg = load();
      cfg.mode = args[1];
      save(cfg);
      std::cout << cfg.mode << "\n";
      return 0;
    }
    if (args[0] == "mcp") return mcp(std::vector<std::string>(args.begin() + 1, args.end()));
    std::string sentence;
    for (std::size_t i = 0; i < args.size(); ++i) {
      if (i) sentence.push_back(' ');
      sentence += args[i];
    }
    Command cmd = parse_sentence(sentence);
    Config cfg = load();
    std::string mode = mode_flag.empty() ? cfg.mode : mode_flag;
    std::string key = cmd.server + "." + cmd.tool;
    if (!yes && gated(mode, cmd.tool, key, cfg.always)) {
      std::cout << "SI-LLM wants to call an MCP tool\n\n  server  " << cmd.server << "\n  tool    " << cmd.tool << "\n";
      for (const auto &arg : cmd.args) std::cout << "  " << arg.first << "\t" << arg.second << "\n";
      std::cout << "\n";
#if !defined(_WIN32)
      if (isatty(0)) {
        std::cout << "Allow? [y]es / [a]lways / [n]o: " << std::flush;
        std::string line;
        if (!std::getline(std::cin, line)) return 2;
        std::string answer = lower(line);
        if (answer == "a" || answer == "always") {
          if (std::find(cfg.always.begin(), cfg.always.end(), key) == cfg.always.end()) cfg.always.push_back(key);
          std::sort(cfg.always.begin(), cfg.always.end());
          save(cfg);
        } else if (answer != "y" && answer != "yes") {
          std::cout << "Not sent.\n";
          return 2;
        }
      } else
#endif
      {
        std::cout << "Not sent. Pass --yes to allow once.\n";
        return 2;
      }
    }
    auto found = cfg.servers.find(cmd.server);
    if (found == cfg.servers.end()) throw std::runtime_error("No MCP server '" + cmd.server + "'. Add one with: si mcp add " + cmd.server + " --url <url>");
    std::cout << call_tool(found->second, cmd.tool, cmd.args) << "\n[xcode] " << key << "\n";
    return 0;
  } catch (const std::exception &err) {
    std::cerr << err.what() << "\n";
    return 1;
  }
}

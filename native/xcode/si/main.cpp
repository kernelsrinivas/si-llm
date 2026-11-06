// Native CLI. It is the model client. It does not run the model.
// The server at SI_URL (default http://127.0.0.1:8765) loads the trained model and calls MCP.
//
//   si mcp add pcb --url http://127.0.0.1:8766/mcp
//   si "desktop motherboard"
//   si --yes "place a resistor r1 at 10 12"

#include <cctype>
#include <cstdlib>
#include <iostream>
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
#else
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace {

std::string lower(std::string text) {
  for (char &c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return text;
}

std::string escape(const std::string &text) {
  std::string out;
  for (char c : text) {
    if (c == '\\' || c == '"') out.push_back('\\');
    if (c == '\n') {
      out += "\\n";
      continue;
    }
    out.push_back(c);
  }
  return out;
}

std::string model_url() {
  if (const char *url = std::getenv("SI_URL")) return url;
  return "http://127.0.0.1:8765";
}

std::string http_exchange(const std::string &method, const std::string &url, const std::string &body) {
  if (url.compare(0, 7, "http://") != 0) throw std::runtime_error("The model server URL must start with http://");
  std::string rest = url.substr(7);
  auto slash = rest.find('/');
  std::string hostport = slash == std::string::npos ? rest : rest.substr(0, slash);
  std::string path = slash == std::string::npos ? "/" : rest.substr(slash);
  if (path.empty()) path = "/";
  std::string host = hostport;
  int port = 80;
  auto colon = hostport.rfind(':');
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
  if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &res) != 0) {
    throw std::runtime_error("The model server host did not resolve.");
  }
  if (connect(fd, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
    freeaddrinfo(res);
    throw std::runtime_error("The model server is not running at " + model_url() + ". Start it, then use si.");
  }
  freeaddrinfo(res);
  std::ostringstream req;
  req << method << " " << path << " HTTP/1.0\r\nHost: " << host << ":" << port
      << "\r\nContent-Type: application/json\r\nContent-Length: " << body.size() << "\r\nConnection: close\r\n\r\n" << body;
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
  if (split == std::string::npos) throw std::runtime_error("The model server returned an empty response.");
  return raw.substr(split + 4);
}

std::string http_get(const std::string &path) { return http_exchange("GET", model_url() + path, ""); }

std::string http_post(const std::string &path, const std::string &body) { return http_exchange("POST", model_url() + path, body); }

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
          if (raw[i] == '\\' && i + 1 < raw.size()) {
            char nch = raw[++i];
            if (nch == 'n') out.push_back('\n');
            else if (nch == 't') out.push_back('\t');
            else if (nch == 'u' && i + 4 < raw.size()) {
              int code = 0;
              for (int k = 0; k < 4; ++k) {
                char h = raw[++i];
                code <<= 4;
                if (h >= '0' && h <= '9') code += h - '0';
                else if (h >= 'a' && h <= 'f') code += h - 'a' + 10;
                else if (h >= 'A' && h <= 'F') code += h - 'A' + 10;
              }
              if (code < 128) out.push_back(static_cast<char>(code));
              else out.push_back('?');
            } else out.push_back(nch);
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

bool json_true(const std::string &raw, const std::string &key) {
  auto at = raw.find("\"" + key + "\"");
  if (at == std::string::npos) return false;
  auto colon = raw.find(':', at);
  if (colon == std::string::npos) return false;
  return raw.compare(colon + 1, 6, " true") == 0 || raw.compare(colon + 1, 5, "true") == 0 || raw.find("true", colon) < colon + 8;
}

void print_turn(const std::string &raw) {
  if (raw.find("\"ok\": false") != std::string::npos || raw.find("\"ok\":false") != std::string::npos) {
    std::string err = json_string_after(raw, "error");
    throw std::runtime_error(err.empty() ? raw : err);
  }
  std::string reply = json_string_after(raw, "reply");
  if (reply.empty()) throw std::runtime_error(raw);
  std::cout << reply << "\n";
  auto commands_at = raw.find("\"commands\"");
  if (commands_at != std::string::npos) {
    auto quote = raw.find('"', raw.find('[', commands_at) + 1);
    auto close = raw.find(']', commands_at);
    if (quote != std::string::npos && quote < close) {
      std::string cmd;
      for (std::size_t i = quote + 1; i < raw.size() && raw[i] != '"'; ++i) cmd.push_back(raw[i]);
      std::string runtime = json_string_after(raw, "runtime");
      if (!cmd.empty()) std::cout << "[" << (runtime.empty() ? "model" : runtime) << "] " << cmd << "\n";
    }
  }
}

std::string ask(const std::string &text, bool yes, const std::string &mode) {
  std::ostringstream body;
  body << "{\"text\":\"" << escape(text) << "\",\"approved\":" << (yes ? "true" : "false");
  if (!mode.empty()) body << ",\"mode\":\"" << escape(mode) << "\"";
  body << "}";
  return http_post("/cli", body.str());
}

struct Choice {
  std::string label;
  std::string prompt;
};

std::string json_object(const std::string &raw, const std::string &key) {
  auto at = raw.find("\"" + key + "\"");
  if (at == std::string::npos) return "";
  auto colon = raw.find(':', at + key.size() + 2);
  if (colon == std::string::npos) return "";
  auto brace = raw.find_first_not_of(" \t\r\n", colon + 1);
  if (brace == std::string::npos || raw[brace] != '{') return "";
  int depth = 0;
  bool inside = false;
  for (std::size_t i = brace; i < raw.size(); ++i) {
    char c = raw[i];
    if (c == '"' && (i == brace || raw[i - 1] != '\\')) inside = !inside;
    if (inside) continue;
    if (c == '{') ++depth;
    if (c == '}' && --depth == 0) return raw.substr(brace, i - brace + 1);
  }
  return "";
}

std::string json_array(const std::string &raw, const std::string &key) {
  auto at = raw.find("\"" + key + "\"");
  if (at == std::string::npos) return "";
  auto colon = raw.find(':', at + key.size() + 2);
  if (colon == std::string::npos) return "";
  auto brace = raw.find_first_not_of(" \t\r\n", colon + 1);
  if (brace == std::string::npos || raw[brace] != '[') return "";
  int depth = 0;
  bool inside = false;
  for (std::size_t i = brace; i < raw.size(); ++i) {
    char c = raw[i];
    if (c == '"' && (i == brace || raw[i - 1] != '\\')) inside = !inside;
    if (inside) continue;
    if (c == '[') ++depth;
    if (c == ']' && --depth == 0) return raw.substr(brace, i - brace + 1);
  }
  return "";
}

std::vector<Choice> choices_in(const std::string &blob) {
  std::vector<Choice> out;
  std::size_t at = 0;
  while ((at = blob.find("\"label\"", at)) != std::string::npos) {
    Choice choice;
    choice.label = json_string_after(blob.substr(at), "label");
    auto prompt_at = blob.find("\"prompt\"", at);
    if (prompt_at == std::string::npos) break;
    choice.prompt = json_string_after(blob.substr(prompt_at), "prompt");
    if (!choice.label.empty() && !choice.prompt.empty()) out.push_back(choice);
    at = prompt_at + 8;
  }
  return out;
}

int recommended_index(const std::string &blob) {
  auto at = blob.find("\"recommendedIndex\"");
  if (at == std::string::npos) return 0;
  auto colon = blob.find(':', at);
  if (colon == std::string::npos) return 0;
  return std::atoi(blob.c_str() + colon + 1);
}

std::string approved(std::string raw, bool yes) {
  if (!json_true(raw, "needsApproval") || yes) return raw;
  print_turn(raw);
#if !defined(_WIN32)
  if (isatty(0)) {
    std::cout << "Allow? [y]es / [a]lways / [n]o: " << std::flush;
    std::string line;
    if (!std::getline(std::cin, line)) return "";
    std::string answer = lower(line);
    std::string decision = (answer == "y" || answer == "yes") ? "allow" : (answer == "a" || answer == "always") ? "always" : "deny";
    if (decision == "deny") {
      std::cout << "Not sent.\n";
      return "";
    }
    return http_post("/approve", std::string("{\"proposalId\":\"") + json_string_after(raw, "proposalId") + "\",\"decision\":\"" + decision + "\"}");
  }
#endif
  std::cout << "Not sent. Pass --yes to allow once.\n";
  return "";
}

std::string pick_line(const std::vector<Choice> &choices, int recommended, const std::string &custom) {
  for (std::size_t i = 0; i < choices.size(); ++i) {
    std::cout << "  " << (i + 1) << ". " << choices[i].label;
    if (static_cast<int>(i) == recommended) std::cout << " (recommended)";
    std::cout << "\n";
  }
  std::cout << custom << std::flush;
  std::string line;
  if (!std::getline(std::cin, line)) return "";
  line = line.substr(0, line.find_last_not_of(" \t\r") + 1);
  if (line.empty()) return "";
  if (line.size() == 1 && line[0] >= '1' && line[0] < '1' + static_cast<char>(choices.size())) {
    return choices[static_cast<std::size_t>(line[0] - '1')].prompt;
  }
  return line;
}

int converse(std::string text, bool yes, const std::string &mode) {
  std::string raw = ask(text, yes, mode);
  raw = approved(raw, yes);
  if (raw.empty()) return 2;
  for (int turn = 0; turn < 8; ++turn) {
    std::string card = json_object(raw, "question");
    if (card.empty()) break;
#if defined(_WIN32)
    break;
#else
    if (!isatty(0)) break;
    print_turn(raw);
    std::string next = pick_line(choices_in(card), recommended_index(card), "Number, or your own value: ");
    if (next.empty()) return 2;
    raw = approved(ask(next, yes, mode), yes);
    if (raw.empty()) return 2;
#endif
  }
  print_turn(raw);
  auto suggestions = choices_in(json_array(raw, "suggestions"));
  if (suggestions.empty()) return 0;
  std::cout << "Next:\n";
#if defined(_WIN32)
  for (std::size_t i = 0; i < suggestions.size(); ++i) std::cout << "  " << (i + 1) << ". " << suggestions[i].label << "\n";
  return 0;
#else
  if (!isatty(0)) {
    for (std::size_t i = 0; i < suggestions.size(); ++i) std::cout << "  " << (i + 1) << ". " << suggestions[i].label << "\n";
    return 0;
  }
  std::string next = pick_line(suggestions, -1, "Number, or enter to stop: ");
  if (next.empty()) return 0;
  raw = approved(ask(next, yes, mode), yes);
  if (raw.empty()) return 2;
  print_turn(raw);
  return 0;
#endif
}

void help() {
  std::cout << "si \"what is a buck converter\"\n"
            << "The server must already be running. Start it with: sh startup.sh\n";
}

int mcp(const std::vector<std::string> &argv) {
  if (argv.empty() || argv[0] == "list" || argv[0] == "ls") {
    std::string raw = http_get("/health");
    auto at = raw.find("\"servers\"");
    if (at == std::string::npos || raw.find("\"id\"", at) == std::string::npos) {
      std::cout << "No MCP connections. Add one with: si mcp add <name> --url <url>\n";
      return 0;
    }
    std::size_t cursor = at;
    while ((cursor = raw.find("\"id\"", cursor)) != std::string::npos) {
      std::string id = json_string_after(raw.substr(cursor), "id");
      if (id.empty() || id == "mcp-client") break;
      std::string transport = json_string_after(raw.substr(cursor), "transport");
      bool ok = json_true(raw.substr(cursor, 400), "ok");
      std::cout << id << "  " << transport << "  " << (ok ? "connected" : "offline") << "\n";
      cursor += 4;
    }
    return 0;
  }
  if (argv[0] == "remove" && argv.size() >= 2) {
    std::string raw = http_post("/mcp/remove", std::string("{\"name\":\"") + escape(argv[1]) + "\"}");
    if (!json_true(raw, "ok")) throw std::runtime_error(json_string_after(raw, "error").empty() ? "remove failed" : json_string_after(raw, "error"));
    std::cout << "removed\n";
    return 0;
  }
  if (argv[0] == "add" && argv.size() >= 4 && (argv[2] == "--url" || argv[2] == "--command")) {
    std::string transport = argv[2] == "--url" ? "http" : "stdio";
    std::string target;
    for (std::size_t i = 3; i < argv.size(); ++i) {
      if (!target.empty()) target.push_back(' ');
      target += argv[i];
    }
    std::ostringstream body;
    body << "{\"name\":\"" << escape(argv[1]) << "\",\"transport\":\"" << transport << "\",\"target\":\"" << escape(target) << "\"}";
    std::string raw = http_post("/mcp/add", body.str());
    if (!json_true(raw, "ok")) {
      std::string err = json_string_after(raw, "error");
      throw std::runtime_error(err.empty() ? "Could not connect." : err);
    }
    std::cout << "connected " << argv[1] << " (" << transport << ")\n";
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
    std::string mode;
    for (int i = 1; i < argc; ++i) {
      std::string arg = argv[i];
      if (arg == "--yes") yes = true;
      else if (arg == "--mode" && i + 1 < argc) mode = argv[++i];
      else args.push_back(arg);
    }
    if (args.empty() || args[0] == "-h" || args[0] == "--help") {
      help();
      return 0;
    }
    if (args[0] == "mode" && args.size() == 2) {
      std::string raw = http_post("/mode", std::string("{\"mode\":\"") + escape(args[1]) + "\"}");
      if (!json_true(raw, "ok")) throw std::runtime_error(json_string_after(raw, "error").empty() ? "Mode is auto, semi, or man." : json_string_after(raw, "error"));
      std::cout << json_string_after(raw, "mode") << "\n";
      return 0;
    }
    if (args[0] == "mcp") return mcp(std::vector<std::string>(args.begin() + 1, args.end()));
    std::string text;
    for (std::size_t i = 0; i < args.size(); ++i) {
      if (i) text.push_back(' ');
      text += args[i];
    }
    return converse(text, yes, mode);
  } catch (const std::exception &err) {
    std::cerr << err.what() << "\n";
    return 1;
  }
}

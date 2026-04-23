# DocPilot — System Design

## What It Does
A terminal-based documentation lookup tool that fetches full docs and usage examples for Python packages, Linux commands, and C++ STL — while you are coding, without leaving the terminal.

---

## Architecture

```
User (terminal)
      |
      v
 ┌──────────────────────────────────────┐
 │              docpilot.py             │
 │                                      │
 │  ┌─────────┐  ┌────────┐  ┌───────┐ │
 │  │ Python  │  │ Linux  │  │  C++  │ │
 │  │Provider │  │Provider│  │Provider│ │
 │  └────┬────┘  └───┬────┘  └───┬───┘ │
 └───────┼───────────┼───────────┼─────┘
         │           │           │
    PyPI API     GitHub TLDR   Built-in
    pydoc CLI    (raw HTTP)    Index
         │           │           │
         └───────────┴───────────┘
                     │
              Rich terminal output
```

---

## Input

| Mode | Example |
|---|---|
| Interactive REPL | `docpilot` → type `cpp vector` |
| One-shot CLI | `docpilot python numpy` |
| Search all | `docpilot search json` |
| Browse C++ | `docpilot list algorithm` |

---

## Data Flow

### Python Provider
1. User types `python requests`
2. HTTP GET → `https://pypi.org/pypi/requests/json`
3. Extract: name, version, summary, install command, description, links
4. Fallback: `python -m pydoc <module>` for stdlib modules (os, json, sys…)
5. Render with Rich panels, Syntax highlighting

### Linux Provider
1. User types `linux grep`
2. HTTP GET → `https://raw.githubusercontent.com/tldr-pages/tldr/main/pages/common/grep.md`
3. Tries platforms: common → linux → osx → windows
4. Parse markdown: extract description and `- example: \`command\`` blocks (handles blank lines between description and command)
5. Render with Rich panels and bash syntax highlighting
6. Always append man page URL as fallback

### C++ Provider
1. User types `cpp vector`
2. Lookup in local `_CPP_INDEX` dict (~60 entries, zero network calls)
3. Returns: category, description, include header, cppreference.com URL
4. Fetch matching example from `_CPP_EXAMPLES` dict
5. Render with C++ syntax highlighting and line numbers

### Search Mode
1. User types `search pandas`
2. Queries all three providers in sequence
3. Builds result table: language, name, description, quick-start command
4. Prints suggestions for deeper lookup

---

## Output

```
C++ docs -> vector
┌─────────────────── C++ Standard Library ────────────────────┐
│ std::vector                                                   │
│ Dynamic array -- O(1) amortised push_back, O(1) random access │
└───────────────────────────────────────────────────────────────┘
Include:  #include <vector>

Usage example:
  1  vector<int> v = {3, 1, 4, 1, 5};
  2  v.push_back(9);     // append
  ...
Reference: https://en.cppreference.com/w/cpp/container/vector
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| C++ index is 100% local | No latency, works offline, always consistent |
| TLDR over man pages | Man pages are dense; TLDR gives copy-paste examples immediately |
| PyPI JSON API | Official, stable, machine-readable, no scraping needed |
| Rich library | Color + syntax highlighting makes it scannable at a glance |
| Interactive REPL | Avoids retyping `python docpilot.py` on every query while coding |

---

## Interview Conclusion

DocPilot solves a real developer friction point: switching to a browser to look up a function signature breaks flow. The architecture is deliberately split into three independent providers with a clean interface — each can be extended or replaced without touching the others. The C++ STL layer requires zero network calls, making it instant even in offline or low-bandwidth environments. The TLDR integration surfaces practical examples rather than dense reference text, which is what developers actually need mid-task. If I were to scale this, I would add a local cache for TLDR pages and PyPI responses with a configurable TTL to make repeated queries fully offline.

# DocPilot - System Design

## What It Does
A terminal-based documentation lookup tool that fetches full docs and usage examples
for Python packages, Linux commands, and C++ STL -- while you code, without leaving
the terminal. Supports an interactive REPL and one-shot CLI mode.

---

## Architecture

```
User (terminal)
      |
      v
+------------------------------------------+
|           docpilot.py                    |
|                                          |
|  +----------+  +----------+  +--------+ |
|  | Python   |  | Linux    |  | C++    | |
|  | Provider |  | Provider |  | Provid.| |
|  +----+-----+  +----+-----+  +---+----+ |
+-------|--------------|-----------+------+
        |              |           |
   PyPI JSON API   GitHub TLDR  Built-in
   + pydoc CLI     raw HTTP     Index dict
        |              |           |
        +------+--------+-----------+
               |
         Rich terminal output
         (panels, syntax highlighting)
```

---

## Input

| Mode            | Example                        |
|-----------------|--------------------------------|
| Interactive REPL| run docpilot, then: cpp vector |
| One-shot CLI    | docpilot python numpy          |
| Search all      | docpilot search json           |
| Browse C++ list | docpilot list algorithm        |

---

## Data Flow

### Python Provider
1. User types: python requests
2. HTTP GET https://pypi.org/pypi/requests/json
3. Extract: name, version, summary, install cmd, links
4. Fallback: python -m pydoc <module> for stdlib (os, json, sys)
5. Render with Rich panels and Syntax blocks

### Linux Provider
1. User types: linux grep
2. HTTP GET tldr-pages on GitHub (common > linux > osx > windows)
3. Parse markdown: description lines and backtick command blocks
4. Skip blank lines between description and command (newer TLDR format)
5. Render with bash syntax highlighting + man page fallback URL

### C++ Provider
1. User types: cpp vector
2. Lookup in local _CPP_INDEX dict (~60 entries, zero network calls)
3. Returns: category, one-line description, include header, cppreference URL
4. Fetch matching example from _CPP_EXAMPLES dict
5. Render with C++ syntax highlighting and line numbers

### Search Mode
1. User types: search pandas
2. Queries all three providers in parallel
3. Builds a Rich table: language, name, description, quick-start command
4. Prints follow-up commands for deeper lookup

---

## Output Sample

```
C++ docs -> vector

| std::vector                                                |
| Dynamic array -- O(1) amortised push_back, random access  |

Include:  #include <vector>

Usage example:
  1  vector<int> v = {3, 1, 4, 1, 5};
  2  v.push_back(9);
  ...

Reference: https://en.cppreference.com/w/cpp/container/vector
```

---

## Key Design Decisions

| Decision                          | Reason                                             |
|-----------------------------------|----------------------------------------------------|
| C++ index is 100% local           | Zero latency, works offline, always consistent     |
| TLDR over man pages               | TLDR gives copy-paste examples; man pages are dense|
| PyPI JSON API                     | Official, stable, no scraping needed               |
| Rich library                      | Color + syntax highlighting for fast scanning      |
| Interactive REPL                  | Avoids retyping the command prefix on every query  |

---

## Interview Conclusion

DocPilot solves a real developer friction point: switching to a browser breaks your
coding flow. The architecture has three independent providers behind a clean interface --
each can be extended without touching the others. The C++ STL layer is entirely local,
making it instant even offline. TLDR surfaces practical examples rather than dense
reference text, which is what developers need mid-task. To scale this, I would add a
local cache for TLDR and PyPI responses with a configurable TTL, making repeated
queries fully offline.

#!/usr/bin/env python3
"""
DocPilot -- instant docs for Python libraries, Linux commands, and C++ STL.

Usage:
    python docpilot.py python <package>      # PyPI or stdlib
    python docpilot.py linux  <command>      # TLDR + man link
    python docpilot.py cpp    <topic>        # C++ STL reference
    python docpilot.py search <term>         # search all three
"""

import sys
import os
import argparse
import subprocess
import json
import re
from typing import Optional, List, Tuple

# ---------- optional imports ----------
try:
    import requests
except ImportError:
    print("ERROR: install dependencies first ->  pip install -r requirements.txt")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.syntax import Syntax
    from rich import box
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    class _Plain:
        def print(self, *a, **kw):
            txt = " ".join(str(x) for x in a)
            print(re.sub(r'\[/?[^\]]*\]', '', txt))
    console = _Plain()

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

# ══════════════════════════════════════════════════════════════════════════════
#  PYTHON  (PyPI + pydoc stdlib)
# ══════════════════════════════════════════════════════════════════════════════

def _pypi(pkg: str) -> Optional[dict]:
    try:
        r = requests.get(f"https://pypi.org/pypi/{pkg}/json", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def _pydoc(mod: str) -> Optional[str]:
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pydoc", mod],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
    except Exception:
        pass
    return None

def show_python(pkg: str):
    console.print(f"\n[bold cyan]Python docs ->[/bold cyan] [bold white]{pkg}[/bold white]\n")

    data = _pypi(pkg)
    if data:
        info   = data["info"]
        name   = info.get("name", pkg)
        ver    = info.get("version", "?")
        summary= info.get("summary") or "No summary."
        desc   = (info.get("description") or "").strip()
        urls   = info.get("project_urls") or {}
        home   = info.get("home_page") or urls.get("Homepage") or ""
        docs   = urls.get("Documentation") or urls.get("Docs") or ""
        req_py = info.get("requires_python") or ""

        if RICH:
            console.print(Panel(
                f"[bold white]{name}[/bold white]  [dim]v{ver}[/dim]\n\n{summary}",
                title="[bold green]PyPI Package[/bold green]", border_style="green"
            ))
        else:
            console.print(f"=== {name} v{ver} ===\n{summary}")

        console.print(f"\n[bold yellow]Install:[/bold yellow]")
        if RICH:
            console.print(Syntax(f"pip install {name}", "bash", theme="monokai"))
        else:
            console.print(f"  pip install {name}")

        if req_py:
            console.print(f"\n[bold yellow]Requires Python:[/bold yellow] {req_py}")

        console.print(f"\n[bold yellow]Links:[/bold yellow]")
        console.print(f"  PyPI   -> https://pypi.org/project/{name}/")
        if home: console.print(f"  Home   -> {home}")
        if docs: console.print(f"  Docs   -> {docs}")

        if desc and desc not in ("UNKNOWN", ""):
            console.print(f"\n[bold yellow]Description (first 2 000 chars):[/bold yellow]")
            # strip non-ASCII so Windows cp1252 terminal does not choke
            snippet = desc[:2000].encode("ascii", errors="replace").decode("ascii")
            console.print(snippet)
        return

    # fallback: stdlib via pydoc
    out = _pydoc(pkg)
    if out:
        if RICH:
            console.print(Panel(out[:4000],
                title=f"[bold green]Python stdlib | {pkg}[/bold green]", border_style="green"))
        else:
            console.print(out[:4000])
        return

    console.print(f"[red]Nothing found for '{pkg}'.[/red]")
    console.print(f"  Search PyPI  -> https://pypi.org/search/?q={pkg}")

# ══════════════════════════════════════════════════════════════════════════════
#  LINUX  (TLDR + man link)
# ══════════════════════════════════════════════════════════════════════════════

_TLDR_PLATFORMS = ["common", "linux", "osx", "windows"]

def _tldr(cmd: str) -> Optional[str]:
    for plat in _TLDR_PLATFORMS:
        url = f"https://raw.githubusercontent.com/tldr-pages/tldr/main/pages/{plat}/{cmd}.md"
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return None

def _parse_tldr(md: str) -> dict:
    lines  = md.strip().splitlines()
    result = {"name": "", "description": [], "examples": []}
    i = 0
    if lines and lines[0].startswith("# "):
        result["name"] = lines[0][2:].strip(); i = 1
    while i < len(lines) and not lines[i].startswith("- "):
        ln = lines[i].strip()
        if ln.startswith(">"):
            result["description"].append(ln[1:].strip())
        elif ln:
            result["description"].append(re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', ln))
        i += 1
    while i < len(lines):
        if lines[i].startswith("- "):
            desc = lines[i][2:].strip().rstrip(":")
            cmds: List[str] = []
            i += 1
            # skip blank lines between description and command
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            while i < len(lines) and lines[i].strip().startswith("`"):
                cmds.append(lines[i].strip().strip("`"))
                i += 1
            result["examples"].append({"desc": desc, "commands": cmds})
        else:
            i += 1
    return result

def show_linux(cmd: str):
    console.print(f"\n[bold cyan]Linux docs ->[/bold cyan] [bold white]{cmd}[/bold white]\n")

    raw = _tldr(cmd)
    if raw:
        p    = _parse_tldr(raw)
        name = p["name"] or cmd
        desc = "\n".join(p["description"])

        if RICH:
            console.print(Panel(
                f"[bold white]{name}[/bold white]\n\n{desc}",
                title="[bold blue]Linux Command  (tldr-pages)[/bold blue]", border_style="blue"
            ))
        else:
            console.print(f"=== {name} ===\n{desc}")

        if p["examples"]:
            console.print(f"\n[bold yellow]Examples:[/bold yellow]\n")
            for ex in p["examples"]:
                console.print(f"  [dim]{ex['desc']}[/dim]")
                for c in ex["commands"]:
                    if RICH:
                        console.print(Syntax(f"  {c}", "bash", theme="monokai"))
                    else:
                        console.print(f"    $ {c}")
                console.print()
    else:
        console.print(f"[yellow]No TLDR page for '{cmd}'.[/yellow]")
        console.print(f"\n  Try locally:  {cmd} --help   |   man {cmd}")

    console.print(f"\n[bold yellow]Full reference:[/bold yellow]")
    console.print(f"  https://tldr.inbrowser.app/pages/common/{cmd}")
    console.print(f"  https://man7.org/linux/man-pages/man1/{cmd}.1.html")

# ══════════════════════════════════════════════════════════════════════════════
#  C++  (built-in STL reference + cppreference links)
# ══════════════════════════════════════════════════════════════════════════════

# (category, one-line description, include header, cppreference path)
_CPP_INDEX: dict = {
    # ── Containers ────────────────────────────────────────────────────────────
    "vector":         ("container", "Dynamic array -- O(1) amortised push_back, O(1) random access",
                       "<vector>",       "container/vector"),
    "array":          ("container", "Fixed-size array on the stack -- zero overhead over raw arrays",
                       "<array>",        "container/array"),
    "deque":          ("container", "Double-ended queue -- O(1) push/pop at both ends",
                       "<deque>",        "container/deque"),
    "list":           ("container", "Doubly-linked list -- O(1) insert/erase anywhere with iterator",
                       "<list>",         "container/list"),
    "forward_list":   ("container", "Singly-linked list -- lower memory than list",
                       "<forward_list>", "container/forward_list"),
    "stack":          ("container", "LIFO adapter (uses deque by default)",
                       "<stack>",        "container/stack"),
    "queue":          ("container", "FIFO adapter (uses deque by default)",
                       "<queue>",        "container/queue"),
    "priority_queue": ("container", "Max-heap adapter -- top() is always the largest element",
                       "<queue>",        "container/priority_queue"),
    "map":            ("container", "Sorted key-value pairs (BST) -- O(log n) all ops",
                       "<map>",          "container/map"),
    "multimap":       ("container", "Sorted map allowing duplicate keys",
                       "<map>",          "container/multimap"),
    "unordered_map":  ("container", "Hash map -- O(1) average lookup/insert/erase",
                       "<unordered_map>","container/unordered_map"),
    "set":            ("container", "Sorted unique elements -- O(log n) all ops",
                       "<set>",          "container/set"),
    "multiset":       ("container", "Sorted set allowing duplicates",
                       "<set>",          "container/multiset"),
    "unordered_set":  ("container", "Hash set -- O(1) average all ops",
                       "<unordered_set>","container/unordered_set"),
    # ── Algorithms ────────────────────────────────────────────────────────────
    "sort":           ("algorithm", "Introsort -- O(n log n), not stable",
                       "<algorithm>",    "algorithm/sort"),
    "stable_sort":    ("algorithm", "Merge sort -- O(n log² n), preserves relative order of equals",
                       "<algorithm>",    "algorithm/stable_sort"),
    "find":           ("algorithm", "Linear search -- returns iterator to first match",
                       "<algorithm>",    "algorithm/find"),
    "find_if":        ("algorithm", "Linear search with predicate",
                       "<algorithm>",    "algorithm/find"),
    "binary_search":  ("algorithm", "Boolean check if value exists in sorted range",
                       "<algorithm>",    "algorithm/binary_search"),
    "lower_bound":    ("algorithm", "First position where value can be inserted (>=) in sorted range",
                       "<algorithm>",    "algorithm/lower_bound"),
    "upper_bound":    ("algorithm", "First position after value (>) in sorted range",
                       "<algorithm>",    "algorithm/upper_bound"),
    "count":          ("algorithm", "Count occurrences of value in range",
                       "<algorithm>",    "algorithm/count"),
    "count_if":       ("algorithm", "Count elements satisfying predicate",
                       "<algorithm>",    "algorithm/count"),
    "copy":           ("algorithm", "Copy range to destination",
                       "<algorithm>",    "algorithm/copy"),
    "fill":           ("algorithm", "Fill range with a value",
                       "<algorithm>",    "algorithm/fill"),
    "transform":      ("algorithm", "Apply function to each element, writing result to output range",
                       "<algorithm>",    "algorithm/transform"),
    "for_each":       ("algorithm", "Apply function to each element (no output)",
                       "<algorithm>",    "algorithm/for_each"),
    "accumulate":     ("numeric",   "Fold/reduce range with binary op (default: sum)",
                       "<numeric>",      "algorithm/accumulate"),
    "reduce":         ("numeric",   "Parallel-friendly accumulate (C++17)",
                       "<numeric>",      "algorithm/reduce"),
    "reverse":        ("algorithm", "Reverse elements in range in-place",
                       "<algorithm>",    "algorithm/reverse"),
    "rotate":         ("algorithm", "Rotate elements so that 'middle' becomes first",
                       "<algorithm>",    "algorithm/rotate"),
    "unique":         ("algorithm", "Remove consecutive duplicates; pair with sort+erase",
                       "<algorithm>",    "algorithm/unique"),
    "remove":         ("algorithm", "Move non-matching elements to front (use with erase)",
                       "<algorithm>",    "algorithm/remove"),
    "remove_if":      ("algorithm", "Move elements not matching predicate to front",
                       "<algorithm>",    "algorithm/remove"),
    "max":            ("algorithm", "Return greater of two values",
                       "<algorithm>",    "algorithm/max"),
    "min":            ("algorithm", "Return lesser of two values",
                       "<algorithm>",    "algorithm/min"),
    "max_element":    ("algorithm", "Iterator to max element in range",
                       "<algorithm>",    "algorithm/max_element"),
    "min_element":    ("algorithm", "Iterator to min element in range",
                       "<algorithm>",    "algorithm/min_element"),
    "swap":           ("algorithm", "Swap two values in O(1)",
                       "<algorithm>",    "algorithm/swap"),
    "next_permutation":("algorithm","Generate next lexicographic permutation in-place",
                        "<algorithm>",   "algorithm/next_permutation"),
    # ── Strings ───────────────────────────────────────────────────────────────
    "string":         ("string",    "Mutable, heap-allocated character sequence",
                       "<string>",       "string/basic_string"),
    "string_view":    ("string",    "Non-owning read-only view into a string (C++17)",
                       "<string_view>",  "string/basic_string_view"),
    "stringstream":   ("io",        "String-based I/O stream -- great for parsing",
                       "<sstream>",      "io/basic_stringstream"),
    # ── Memory / Smart Pointers ───────────────────────────────────────────────
    "unique_ptr":     ("memory",    "Sole-owner smart pointer -- zero overhead, move-only",
                       "<memory>",       "memory/unique_ptr"),
    "shared_ptr":     ("memory",    "Ref-counted shared ownership smart pointer",
                       "<memory>",       "memory/shared_ptr"),
    "weak_ptr":       ("memory",    "Non-owning observer of a shared_ptr (breaks cycles)",
                       "<memory>",       "memory/weak_ptr"),
    "make_unique":    ("memory",    "Factory for unique_ptr (exception-safe)",
                       "<memory>",       "memory/make_unique"),
    "make_shared":    ("memory",    "Factory for shared_ptr (single allocation)",
                       "<memory>",       "memory/make_shared"),
    # ── I/O ───────────────────────────────────────────────────────────────────
    "cout":           ("io",        "Standard output stream",
                       "<iostream>",     "io/cout"),
    "cin":            ("io",        "Standard input stream",
                       "<iostream>",     "io/cin"),
    "cerr":           ("io",        "Standard error stream (unbuffered)",
                       "<iostream>",     "io/cerr"),
    "fstream":        ("io",        "File stream (read+write)",
                       "<fstream>",      "io/basic_fstream"),
    "ifstream":       ("io",        "File input stream",
                       "<fstream>",      "io/basic_ifstream"),
    "ofstream":       ("io",        "File output stream",
                       "<fstream>",      "io/basic_ofstream"),
    # ── Threading ─────────────────────────────────────────────────────────────
    "thread":         ("thread",    "Represents a thread of execution",
                       "<thread>",       "thread/thread"),
    "mutex":          ("thread",    "Mutual exclusion -- use with lock_guard or unique_lock",
                       "<mutex>",        "thread/mutex"),
    "lock_guard":     ("thread",    "RAII mutex lock -- unlocks on scope exit",
                       "<mutex>",        "thread/lock_guard"),
    "unique_lock":    ("thread",    "Flexible mutex ownership (can unlock/relock)",
                       "<mutex>",        "thread/unique_lock"),
    "condition_variable":("thread", "Block and notify threads waiting on a condition",
                       "<condition_variable>","thread/condition_variable"),
    "atomic":         ("thread",    "Lock-free atomic operations on integral/pointer types",
                       "<atomic>",       "atomic/atomic"),
    "async":          ("thread",    "Run function asynchronously, get result via future",
                       "<future>",       "thread/async"),
    "future":         ("thread",    "Hold result of an asynchronous operation",
                       "<future>",       "thread/future"),
    # ── Utilities ─────────────────────────────────────────────────────────────
    "pair":           ("utility",   "Holds two heterogeneous values",
                       "<utility>",      "utility/pair"),
    "tuple":          ("utility",   "Holds N heterogeneous values",
                       "<tuple>",        "utility/tuple"),
    "optional":       ("utility",   "Value that may or may not be present (C++17)",
                       "<optional>",     "utility/optional"),
    "variant":        ("utility",   "Type-safe union -- holds one of N types (C++17)",
                       "<variant>",      "utility/variant"),
    "any":            ("utility",   "Type-erased container for any copyable type (C++17)",
                       "<any>",          "utility/any"),
    "function":       ("functional","General-purpose polymorphic function wrapper",
                       "<functional>",   "utility/functional/function"),
    "bind":           ("functional","Bind arguments to a callable, producing a new callable",
                       "<functional>",   "utility/functional/bind"),
    "lambda":         ("language",  "Anonymous inline function -- captures local variables",
                       "--",              "language/lambda"),
    "move":           ("utility",   "Cast to rvalue reference to enable move semantics",
                       "<utility>",      "utility/move"),
    "forward":        ("utility",   "Perfect-forward argument (preserve value category)",
                       "<utility>",      "utility/forward"),
    "chrono":         ("chrono",    "Type-safe time durations and clocks (C++11)",
                       "<chrono>",       "chrono"),
    "filesystem":     ("filesystem","File system operations -- paths, dir iteration (C++17)",
                       "<filesystem>",   "filesystem"),
    "regex":          ("regex",     "ECMAScript-compatible regular expressions",
                       "<regex>",        "regex"),
    "span":           ("span",      "Non-owning view of a contiguous sequence (C++20)",
                       "<span>",         "container/span"),
}

# Compact but complete usage examples
_CPP_EXAMPLES: dict = {
"vector": """\
#include <vector>
#include <algorithm>
using namespace std;

vector<int> v = {3, 1, 4, 1, 5};
v.push_back(9);          // append
v.pop_back();            // remove last
v.insert(v.begin(), 0);  // insert at front
v.erase(v.begin());      // erase at front
v[2];  v.at(2);          // access (at() bounds-checks)
v.size(); v.empty();
v.front(); v.back();
sort(v.begin(), v.end()); // sort ascending
v.clear();
""",
"array": """\
#include <array>
using namespace std;

array<int, 5> a = {1, 2, 3, 4, 5};  // size fixed at compile time
a[2];  a.at(2);
a.size();   // 5 -- constexpr
a.front(); a.back();
a.fill(0);  // set all to 0
""",
"deque": """\
#include <deque>
using namespace std;

deque<int> dq = {2, 3, 4};
dq.push_front(1);  dq.push_back(5);
dq.pop_front();    dq.pop_back();
dq[0]; dq.front(); dq.back();
""",
"list": """\
#include <list>
using namespace std;

list<int> lst = {1, 2, 3};
lst.push_front(0); lst.push_back(4);
auto it = lst.begin(); ++it;
lst.insert(it, 99);   // insert before iterator
lst.erase(it);         // erase at iterator -- O(1)
lst.sort();            // member sort (no random access)
lst.reverse();
""",
"stack": """\
#include <stack>
using namespace std;

stack<int> s;
s.push(10); s.push(20); s.push(30);
s.top();    // 30
s.pop();    // removes 30
s.empty();  s.size();
""",
"queue": """\
#include <queue>
using namespace std;

queue<int> q;
q.push(1); q.push(2); q.push(3);
q.front(); // 1 (oldest)
q.back();  // 3 (newest)
q.pop();   // removes front
q.empty(); q.size();
""",
"priority_queue": """\
#include <queue>
#include <vector>
using namespace std;

// Max-heap (default)
priority_queue<int> pq;
pq.push(3); pq.push(1); pq.push(4);
pq.top();   // 4 (largest)
pq.pop();   // removes 4

// Min-heap
priority_queue<int, vector<int>, greater<int>> minpq;
minpq.push(3); minpq.push(1);
minpq.top();  // 1 (smallest)
""",
"map": """\
#include <map>
using namespace std;

map<string, int> m;
m["alice"] = 30;          // insert or update
m.insert({"bob", 25});
m.count("alice");         // 1 if present, 0 if not
m.at("alice");            // access (throws if missing)
m["charlie"];             // inserts 0 if missing -- be careful!
m.erase("bob");

for (auto& [k, v] : m)   // sorted by key
    cout << k << ": " << v << "\\n";

auto it = m.find("alice");
if (it != m.end()) cout << it->second;
""",
"unordered_map": """\
#include <unordered_map>
using namespace std;

unordered_map<string, int> um;
um["alice"] = 30;         // O(1) avg insert
um.count("alice");        // O(1) avg lookup
um.erase("alice");        // O(1) avg erase

// reserve buckets upfront to avoid rehashing
um.reserve(1000);

for (auto& [k, v] : um)  // order not guaranteed
    cout << k << ": " << v << "\\n";
""",
"set": """\
#include <set>
using namespace std;

set<int> s = {3, 1, 4, 1, 5}; // {1, 3, 4, 5} -- sorted unique
s.insert(2);
s.erase(3);
s.count(4);   // 0 or 1
auto it = s.find(4);       // iterator or end()
auto lo = s.lower_bound(3); // first >= 3
auto hi = s.upper_bound(3); // first >  3
""",
"unordered_set": """\
#include <unordered_set>
using namespace std;

unordered_set<int> us = {1, 2, 3, 4, 5};
us.insert(6);
us.erase(1);
us.count(3);   // 1 if present, 0 if not -- O(1) avg
""",
"sort": """\
#include <algorithm>
#include <vector>
using namespace std;

vector<int> v = {5, 2, 8, 1};

sort(v.begin(), v.end());                      // ascending
sort(v.begin(), v.end(), greater<int>());      // descending
sort(v.begin(), v.end(), [](int a, int b){     // custom
    return abs(a) < abs(b);
});

// partial sort: put 3 smallest at front
partial_sort(v.begin(), v.begin()+3, v.end());

// sort struct / class
struct P { string name; int age; };
vector<P> people = {{"Alice",30},{"Bob",25}};
sort(people.begin(), people.end(),
     [](const P& a, const P& b){ return a.age < b.age; });
""",
"binary_search": """\
#include <algorithm>
#include <vector>
using namespace std;

vector<int> v = {1, 2, 3, 4, 5}; // MUST be sorted

binary_search(v.begin(), v.end(), 3);  // true
binary_search(v.begin(), v.end(), 9);  // false

// Get position
auto lb = lower_bound(v.begin(), v.end(), 3); // first >= 3
auto ub = upper_bound(v.begin(), v.end(), 3); // first >  3
int idx = lb - v.begin();  // index
""",
"accumulate": """\
#include <numeric>
#include <vector>
#include <functional>
using namespace std;

vector<int> v = {1, 2, 3, 4, 5};

int   sum     = accumulate(v.begin(), v.end(), 0);         // 15
int   product = accumulate(v.begin(), v.end(), 1, multiplies<int>()); // 120
string joined = accumulate(v.begin(), v.end(), string{},
    [](string acc, int x){ return acc + to_string(x) + ","; });
""",
"string": """\
#include <string>
using namespace std;

string s = "hello world";
s.length();  s.size();     s.empty();
s[0];        s.at(0);      // 'h'
s.front();   s.back();
s += " cpp";               // append
s.substr(6, 5);            // "world"
s.find("world");           // 6  (or string::npos)
s.rfind('l');              // last 'l'
s.replace(0, 5, "hi");     // "hi world"
s.erase(0, 3);             // remove first 3 chars
s.insert(0, "hey ");
to_string(42);             // int -> string
stoi("123");               // string -> int
stod("3.14");              // string -> double
s.c_str();                 // C-style const char*
""",
"stringstream": """\
#include <sstream>
#include <string>
using namespace std;

// Build a string
ostringstream oss;
oss << "Hello " << 42 << " world";
string result = oss.str();

// Parse a string
string line = "10 20 30";
istringstream iss(line);
int a, b, c;
iss >> a >> b >> c;   // a=10, b=20, c=30

// Split by delimiter
string token;
while (getline(iss, token, ',')) { /* each token */ }
""",
"unique_ptr": """\
#include <memory>
using namespace std;

// Create
auto p = make_unique<int>(42);
auto arr = make_unique<int[]>(10);   // array

*p;          // dereference
p.get();     // raw pointer (don't delete this!)
p.reset();   // release and nullify
auto q = move(p);  // transfer ownership (p becomes null)

// Custom deleter
auto fp = unique_ptr<FILE, decltype(&fclose)>(
    fopen("file.txt", "r"), fclose);
""",
"shared_ptr": """\
#include <memory>
using namespace std;

auto p1 = make_shared<int>(42);
auto p2 = p1;           // both own the int now
p1.use_count();         // 2
*p1 = 100;
p1.reset();             // p1 releases; p2 still owns
p2.use_count();         // 1

// weak_ptr -- observe without owning (breaks cycles)
weak_ptr<int> w = p2;
if (auto locked = w.lock()) { /* use *locked */ }
""",
"thread": """\
#include <thread>
#include <mutex>
#include <iostream>
using namespace std;

mutex mtx;

void worker(int id) {
    lock_guard<mutex> lock(mtx);   // auto-unlock on scope exit
    cout << "Thread " << id << "\\n";
}

int main() {
    vector<thread> threads;
    for (int i = 0; i < 4; i++)
        threads.emplace_back(worker, i);
    for (auto& t : threads) t.join();
}
""",
"atomic": """\
#include <atomic>
#include <thread>
using namespace std;

atomic<int>  counter{0};
atomic<bool> done{false};

// Safe to read/write from multiple threads without a mutex
counter++;                        // atomic increment
counter.fetch_add(5);
counter.fetch_sub(1);
int old = counter.exchange(0);    // swap; returns old value
int expected = 5;
counter.compare_exchange_strong(expected, 10); // CAS
""",
"async": """\
#include <future>
#include <iostream>
using namespace std;

int expensive_calc(int x) { return x * x; }

// Launch on a separate thread
future<int> fut = async(launch::async, expensive_calc, 6);

// Do other work here...

int result = fut.get();  // blocks until ready -> 36
""",
"pair": """\
#include <utility>
using namespace std;

pair<int, string> p = {1, "hello"};
p.first;   // 1
p.second;  // "hello"
auto p2 = make_pair(3.14, true);

// common in map iteration
map<string,int> m;
for (auto& [k, v] : m) { /* structured bindings (C++17) */ }
""",
"tuple": """\
#include <tuple>
using namespace std;

auto t = make_tuple(1, "hello", 3.14);
get<0>(t);   // 1
get<1>(t);   // "hello"
auto [a, b, c] = t;  // structured bindings (C++17)
tuple_size<decltype(t)>::value;   // 3
""",
"optional": """\
#include <optional>
using namespace std;

optional<int> find_value(bool cond) {
    if (cond) return 42;
    return nullopt;           // empty
}

auto v = find_value(true);
if (v.has_value())  cout << *v;     // dereference
v.value_or(-1);                     // default if empty
""",
"variant": """\
#include <variant>
#include <string>
using namespace std;

variant<int, double, string> v = 42;
v = "hello";    // change active type
get<string>(v); // "hello" -- throws if wrong type
get_if<int>(&v); // nullptr if not int, else pointer

visit([](auto& x){ cout << x; }, v);  // polymorphic visitor
""",
"function": """\
#include <functional>
using namespace std;

function<int(int, int)> add = [](int a, int b){ return a+b; };
add(2, 3); // 5

// Store any callable with matching signature
function<void(int)> callback;
callback = [](int x){ cout << x; };
callback(42);
""",
"lambda": """\
// Basic lambda
auto add = [](int a, int b) -> int { return a + b; };

// Capture by value / reference
int x = 10;
auto by_val = [x]()  { return x; };    // copy of x
auto by_ref = [&x]() { return x; };    // reference to x
auto all    = [=]()  { return x; };    // all by value
auto allref = [&]()  { return x; };    // all by reference

// Generic lambda (C++14)
auto print = [](auto v){ cout << v; };

// Immediately invoked
int result = [](int n){ return n * n; }(7);   // 49
""",
"regex": """\
#include <regex>
#include <string>
using namespace std;

string text = "Hello World 2024";
regex  pat(R"(\\d+)");                     // raw string for patterns

// Match whole string
regex_match("2024", pat);                  // true

// Search anywhere
smatch m;
if (regex_search(text, m, pat))
    cout << m[0];                          // "2024"

// Replace
string result = regex_replace(text, pat, "YEAR");

// Iterate all matches
sregex_iterator it(text.begin(), text.end(), pat), end;
for (; it != end; ++it) cout << (*it)[0] << " ";
""",
"chrono": """\
#include <chrono>
#include <thread>
using namespace std;
using namespace chrono;

auto start = steady_clock::now();

this_thread::sleep_for(milliseconds(100));  // sleep

auto end  = steady_clock::now();
auto diff = duration_cast<milliseconds>(end - start).count();
cout << diff << " ms\\n";

// Literals (C++14)
auto t = 500ms;   auto t2 = 2s;   auto t3 = 1min;
""",
"filesystem": """\
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

fs::path p = "/home/user/data.txt";
p.filename();   // "data.txt"
p.stem();       // "data"
p.extension();  // ".txt"
p.parent_path();

fs::exists(p);
fs::is_directory(p);
fs::file_size(p);
fs::create_directories("a/b/c");
fs::remove("file.txt");
fs::copy("src.txt", "dst.txt");
fs::rename("old.txt", "new.txt");

for (auto& entry : fs::directory_iterator("."))
    cout << entry.path() << "\\n";
""",
"ifstream": """\
#include <fstream>
#include <string>
using namespace std;

ifstream fin("data.txt");
if (!fin) { cerr << "Cannot open\\n"; return 1; }

string line;
while (getline(fin, line)) { /* process line */ }

// Or read token by token
int n;
while (fin >> n) { /* process n */ }

fin.close();   // optional -- closed by destructor
""",
"ofstream": """\
#include <fstream>
using namespace std;

ofstream fout("out.txt");            // create/overwrite
// ofstream fout("out.txt", ios::app); // append mode
if (!fout) { cerr << "Cannot open\\n"; return 1; }

fout << "Hello " << 42 << "\\n";
fout.flush();  // force write to disk (optional)
// auto-closed when fout goes out of scope
""",
}

def show_cpp(topic: str):
    console.print(f"\n[bold cyan]C++ docs ->[/bold cyan] [bold white]{topic}[/bold white]\n")
    key = topic.lower()

    if key in _CPP_INDEX:
        cat, desc, header, ref_path = _CPP_INDEX[key]
        std_name = f"std::{key}" if cat != "language" else key

        if RICH:
            console.print(Panel(
                f"[bold white]{std_name}[/bold white]\n\n{desc}",
                title="[bold magenta]C++ Standard Library[/bold magenta]", border_style="magenta"
            ))
        else:
            console.print(f"=== {std_name} ===\n{desc}")

        if header != "--":
            console.print(f"\n[bold yellow]Include:[/bold yellow]  #include {header}")

        if key in _CPP_EXAMPLES:
            console.print(f"\n[bold yellow]Usage example:[/bold yellow]")
            if RICH:
                console.print(Syntax(_CPP_EXAMPLES[key].strip(), "cpp",
                                      theme="monokai", line_numbers=True))
            else:
                console.print(_CPP_EXAMPLES[key])

        console.print(f"\n[bold yellow]Reference:[/bold yellow]")
        console.print(f"  https://en.cppreference.com/w/cpp/{ref_path}")
    else:
        console.print(f"[yellow]'{topic}' not in built-in index -- try online:[/yellow]")
        console.print(f"  https://en.cppreference.com/mwiki/index.php?search={key}")
        console.print(f"  https://en.cppreference.com/w/cpp/algorithm/{key}")
        console.print(f"  https://en.cppreference.com/w/cpp/container/{key}")

# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH  (across all three)
# ══════════════════════════════════════════════════════════════════════════════

def show_search(term: str):
    console.print(f"\n[bold cyan]Searching all languages for:[/bold cyan] [bold white]{term}[/bold white]\n")
    key  = term.lower()
    rows = []

    # Python / PyPI
    console.print("[dim]  checking PyPI...[/dim]")
    data = _pypi(term)
    if data:
        info = data["info"]
        rows.append(("Python / PyPI", info["name"],
                      (info.get("summary") or "")[:80],
                      f"pip install {info['name']}"))

    # C++ built-in
    if key in _CPP_INDEX:
        cat, desc, header, _ = _CPP_INDEX[key]
        rows.append(("C++ STL", f"std::{key}", desc[:80], f"#include {header}"))

    # Linux TLDR
    console.print("[dim]  checking TLDR...[/dim]")
    raw = _tldr(term)
    if raw:
        p = _parse_tldr(raw)
        desc_short = " ".join(p["description"])[:80]
        rows.append(("Linux", p["name"] or term, desc_short, f"{term} --help"))

    console.print()  # clear the [dim] lines visually

    if rows:
        if RICH:
            t = Table(title=f"Results for  '{term}'", box=box.ROUNDED,
                      show_header=True, header_style="bold cyan")
            t.add_column("Language",    style="cyan",  no_wrap=True)
            t.add_column("Name",        style="white bold")
            t.add_column("Description", style="dim")
            t.add_column("Quick start", style="green")
            for r in rows:
                t.add_row(*r)
            console.print(t)
        else:
            for lang, name, desc, use in rows:
                console.print(f"[{lang}]  {name}  --  {desc}  ->  {use}")

        console.print(f"\n[bold]Run one of these for full docs:[/bold]")
        for lang, name, _, _ in rows:
            raw  = lang.split("/")[0].strip().lower()
            cmd  = "cpp" if "c++" in raw else raw
            cname = name.replace("std::", "")
            console.print(f"  python docpilot.py {cmd} {cname}")
    else:
        console.print(f"[red]Nothing found for '{term}'.[/red]")
        console.print(f"  PyPI       -> https://pypi.org/search/?q={term}")
        console.print(f"  cppreference -> https://en.cppreference.com/mwiki/index.php?search={term}")
        console.print(f"  TLDR       -> https://tldr.inbrowser.app/?search={term}")

# ══════════════════════════════════════════════════════════════════════════════
#  LIST command  -- show all built-in C++ topics
# ══════════════════════════════════════════════════════════════════════════════

def show_list(filter_cat: Optional[str] = None):
    cats: dict = {}
    for name, (cat, desc, header, _) in sorted(_CPP_INDEX.items()):
        if filter_cat and filter_cat.lower() not in cat.lower():
            continue
        cats.setdefault(cat, []).append((name, desc, header))

    for cat, items in sorted(cats.items()):
        if RICH:
            t = Table(title=f"C++ | {cat}", box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Name",    style="white bold")
            t.add_column("Header",  style="green")
            t.add_column("Summary", style="dim")
            for name, desc, header in items:
                t.add_row(name, header, desc)
            console.print(t)
        else:
            console.print(f"\n=== {cat} ===")
            for name, desc, header in items:
                console.print(f"  {name:<20} {header:<22} {desc}")

# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        prog="docpilot",
        description="Instant docs for Python, Linux, and C++",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  python docpilot.py python numpy          # PyPI package
  python docpilot.py python os             # stdlib module
  python docpilot.py linux grep            # Linux command
  python docpilot.py linux curl
  python docpilot.py cpp vector            # C++ container
  python docpilot.py cpp sort              # C++ algorithm
  python docpilot.py cpp unique_ptr        # smart pointer
  python docpilot.py search requests       # search all 3 langs
  python docpilot.py list                  # all C++ STL topics
  python docpilot.py list container        # filter by category
""")

    sub = ap.add_subparsers(dest="cmd")

    py  = sub.add_parser("python",  aliases=["py"],          help="Python package or stdlib module")
    py.add_argument("name")

    lx  = sub.add_parser("linux",   aliases=["lx","cmd"],    help="Linux/Unix command (TLDR)")
    lx.add_argument("name")

    cpp = sub.add_parser("cpp",     aliases=["c++","cxx"],   help="C++ STL topic")
    cpp.add_argument("name")

    sr  = sub.add_parser("search",  aliases=["s","find"],    help="Search all languages")
    sr.add_argument("term")

    ls  = sub.add_parser("list",                             help="List all built-in C++ topics")
    ls.add_argument("category", nargs="?",
                    help="Optional filter: container, algorithm, memory, thread …")

    args = ap.parse_args()

    if args.cmd in ("python", "py"):
        show_python(args.name)
    elif args.cmd in ("linux", "lx", "cmd"):
        show_linux(args.name)
    elif args.cmd in ("cpp", "c++", "cxx"):
        show_cpp(args.name)
    elif args.cmd in ("search", "s", "find"):
        show_search(args.term)
    elif args.cmd == "list":
        show_list(args.category)
    else:
        _repl()


def _repl():
    """Interactive mode — runs when docpilot is started with no arguments."""
    if RICH:
        console.print(Panel(
            "[bold white]DocPilot[/bold white]  [dim]—  instant docs while you code[/dim]\n\n"
            "[cyan]python[/cyan] [white]<pkg>[/white]     PyPI package or stdlib module\n"
            "[cyan]linux[/cyan]  [white]<cmd>[/white]     Linux command  (TLDR + man link)\n"
            "[cyan]cpp[/cyan]    [white]<topic>[/white]   C++ STL reference + code example\n"
            "[cyan]search[/cyan] [white]<term>[/white]    Search all three languages\n"
            "[cyan]list[/cyan]              Browse all C++ STL topics\n\n"
            "[dim]Type  q  or  exit  to quit.[/dim]",
            title="[bold green]DocPilot[/bold green]",
            border_style="green"
        ))
    else:
        print("DocPilot — type: python <pkg> | linux <cmd> | cpp <topic> | search <term> | list | q")

    while True:
        try:
            if RICH:
                raw = console.input("\n[bold green]>[/bold green] ").strip()
            else:
                raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        if not raw:
            continue
        if raw.lower() in ("q", "quit", "exit", "bye"):
            console.print("[dim]bye[/dim]")
            break

        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        rest  = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("python", "py"):
            if rest:
                show_python(rest)
            else:
                console.print("[red]Usage:  python <package>[/red]")
        elif cmd in ("linux", "lx", "cmd"):
            if rest:
                show_linux(rest)
            else:
                console.print("[red]Usage:  linux <command>[/red]")
        elif cmd in ("cpp", "c++", "cxx"):
            if rest:
                show_cpp(rest)
            else:
                console.print("[red]Usage:  cpp <topic>[/red]")
        elif cmd in ("search", "s", "find"):
            if rest:
                show_search(rest)
            else:
                console.print("[red]Usage:  search <term>[/red]")
        elif cmd == "list":
            show_list(rest or None)
        elif cmd in ("help", "h", "?"):
            console.print("[cyan]python[/cyan] <pkg>  |  [cyan]linux[/cyan] <cmd>  |  [cyan]cpp[/cyan] <topic>  |  [cyan]search[/cyan] <term>  |  [cyan]list[/cyan]  |  [cyan]q[/cyan]")
        else:
            # try auto-detect: single word -> search all
            console.print(f"[dim]Searching all languages for '{raw}'...[/dim]")
            show_search(raw)


if __name__ == "__main__":
    main()

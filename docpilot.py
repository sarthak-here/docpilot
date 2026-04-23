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
#  OLLAMA  (local LLM for AI-powered examples and tech-stack advisor)
# ══════════════════════════════════════════════════════════════════════════════

OLLAMA_URL = "http://localhost:11434"
# Ranked preference: best code models first
_PREFERRED_MODELS = [
    "gemma4", "gemma3", "gemma2",
    "llama3.1", "llama3", "llama3.2",
    "mistral", "phi3", "phi4", "deepseek-coder",
]


def _ollama_available() -> tuple:
    """Return (True, model_name) if Ollama is running and has a usable model."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return False, ""
        installed = [m["name"].split(":")[0] for m in r.json().get("models", [])]
        for pref in _PREFERRED_MODELS:
            if pref in installed:
                return True, r.json()["models"][
                    [m["name"].split(":")[0] for m in r.json()["models"]].index(pref)
                ]["name"]
        if installed:
            return True, r.json()["models"][0]["name"]
    except Exception:
        pass
    return False, ""


def _ollama_generate(prompt: str, model: str, timeout: int = 60) -> Optional[str]:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  PYTHON  (PyPI + pydoc stdlib)
# ══════════════════════════════════════════════════════════════════════════════

# Canonical import line + usage examples for popular packages/modules.
# Shown at the very top of every result so you can copy-paste immediately.
_PYTHON_QUICKSTART: dict = {
    "numpy": {
        "import": "import numpy as np",
        "examples": [
            "arr = np.array([1, 2, 3, 4, 5])",
            "np.zeros((3, 3))           # 3x3 zero matrix",
            "np.ones((2, 4))            # 2x4 ones matrix",
            "np.arange(0, 10, 2)        # [0, 2, 4, 6, 8]",
            "np.linspace(0, 1, 5)       # 5 evenly spaced values",
            "arr.shape  arr.dtype  arr.ndim",
            "arr.reshape(5, 1)          # change shape",
            "np.dot(a, b)               # matrix multiply",
            "np.sum(arr)  np.mean(arr)  np.std(arr)",
            "arr[arr > 2]               # boolean indexing",
        ],
    },
    "pandas": {
        "import": "import pandas as pd",
        "examples": [
            "df = pd.read_csv('file.csv')",
            "df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4]})",
            "df.head()  df.tail()  df.info()  df.describe()",
            "df['col1']                 # select column -> Series",
            "df[['col1', 'col2']]       # select multiple columns",
            "df[df['col1'] > 1]         # filter rows",
            "df.groupby('col1').sum()",
            "df.merge(df2, on='id')",
            "df.to_csv('out.csv', index=False)",
        ],
    },
    "matplotlib": {
        "import": "import matplotlib.pyplot as plt",
        "examples": [
            "plt.plot([1, 2, 3], [4, 5, 6])    # line chart",
            "plt.scatter(x, y)                  # scatter plot",
            "plt.bar(['A', 'B', 'C'], [10, 20, 15])",
            "plt.hist(data, bins=20)",
            "plt.xlabel('X')  plt.ylabel('Y')  plt.title('Title')",
            "plt.legend(['series1'])  plt.grid(True)",
            "plt.savefig('chart.png', dpi=150)",
            "plt.show()",
            "fig, axes = plt.subplots(1, 2, figsize=(10, 4))  # subplots",
        ],
    },
    "requests": {
        "import": "import requests",
        "examples": [
            "r = requests.get('https://api.example.com/data')",
            "r = requests.post('https://api.example.com/', json={'key': 'val'})",
            "r.status_code              # 200",
            "r.json()                   # parse JSON response",
            "r.text                     # raw text",
            "r.raise_for_status()       # raise exception on 4xx/5xx",
            "r = requests.get(url, headers={'Authorization': 'Bearer TOKEN'},",
            "                 params={'q': 'search', 'page': 1})",
        ],
    },
    "os": {
        "import": "import os",
        "examples": [
            "os.getcwd()                # current directory",
            "os.listdir('.')            # list files in directory",
            "os.path.join('dir', 'file.txt')",
            "os.path.exists('/path')    # True/False",
            "os.path.isfile('f.txt')    # is it a file?",
            "os.makedirs('a/b/c', exist_ok=True)",
            "os.remove('file.txt')",
            "os.rename('old.txt', 'new.txt')",
            "os.environ.get('HOME', '/tmp')  # env variable",
        ],
    },
    "sys": {
        "import": "import sys",
        "examples": [
            "sys.argv                   # list of command line args",
            "sys.argv[0]                # script name",
            "sys.exit(0)                # exit program",
            "sys.path.append('/mydir')  # add to module search path",
            "sys.version                # Python version string",
            "sys.platform               # 'win32', 'linux', 'darwin'",
            "sys.stdout.write('hello\\n')",
        ],
    },
    "json": {
        "import": "import json",
        "examples": [
            "json.dumps({'key': 'val', 'n': 42})     # dict -> string",
            "json.dumps(data, indent=2)              # pretty-print",
            "data = json.loads('{\"key\": \"value\"}')  # string -> dict",
            "with open('data.json', 'w') as f:",
            "    json.dump(data, f, indent=2)        # write to file",
            "with open('data.json') as f:",
            "    data = json.load(f)                 # read from file",
        ],
    },
    "re": {
        "import": "import re",
        "examples": [
            "re.search(r'\\d+', 'abc123')     # Match object or None",
            "re.match(r'\\d+', '123abc')      # match at start only",
            "re.findall(r'\\d+', 'a1 b2 c3') # ['1', '2', '3']",
            "re.sub(r'\\s+', ' ', text)       # replace whitespace runs",
            "re.split(r',\\s*', 'a, b, c')   # ['a', 'b', 'c']",
            "m = re.search(r'(\\w+)@(\\w+)', 'user@host')",
            "m.group(1)   # 'user'   m.group(2)  # 'host'",
            "pat = re.compile(r'\\d+')        # compile for reuse",
        ],
    },
    "datetime": {
        "import": "from datetime import datetime, date, timedelta",
        "examples": [
            "datetime.now()                   # current date+time",
            "datetime.utcnow()                # UTC datetime",
            "date.today()                     # today's date only",
            "dt.strftime('%Y-%m-%d %H:%M')    # format to string",
            "datetime.strptime('2024-01-15', '%Y-%m-%d')  # parse",
            "dt + timedelta(days=7)           # add 7 days",
            "(dt2 - dt1).days                 # difference in days",
        ],
    },
    "pathlib": {
        "import": "from pathlib import Path",
        "examples": [
            "p = Path('folder/file.txt')",
            "p.name          # 'file.txt'",
            "p.stem          # 'file'",
            "p.suffix        # '.txt'",
            "p.parent        # Path('folder')",
            "p.exists()  p.is_file()  p.is_dir()",
            "p.read_text()             # file contents as string",
            "p.write_text('hello')     # write file",
            "p.mkdir(parents=True, exist_ok=True)",
            "list(p.glob('**/*.py'))   # recursive glob",
        ],
    },
    "collections": {
        "import": "from collections import Counter, defaultdict, deque, namedtuple",
        "examples": [
            "c = Counter(['a', 'b', 'a', 'c'])   # {'a':2,'b':1,'c':1}",
            "c.most_common(2)            # [('a',2),('b',1)]",
            "dd = defaultdict(list)",
            "dd['key'].append(1)         # no KeyError if missing",
            "dq = deque([1, 2, 3])",
            "dq.appendleft(0)  dq.popleft()   # O(1) both ends",
            "Point = namedtuple('Point', ['x', 'y'])",
            "p = Point(1, 2)  # p.x -> 1  p.y -> 2",
        ],
    },
    "itertools": {
        "import": "import itertools",
        "examples": [
            "list(itertools.chain([1,2], [3,4]))        # [1,2,3,4]",
            "list(itertools.chain.from_iterable([[1],[2]]))  # flatten",
            "list(itertools.combinations([1,2,3], 2))  # pairs",
            "list(itertools.permutations([1,2,3], 2))  # ordered pairs",
            "list(itertools.product([0,1], repeat=3))  # cartesian product",
            "list(itertools.accumulate([1,2,3,4]))      # [1,3,6,10]",
            "list(itertools.islice(range(100), 5, 10)) # slice of iter",
        ],
    },
    "functools": {
        "import": "import functools",
        "examples": [
            "@functools.lru_cache(maxsize=128)",
            "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
            "",
            "functools.reduce(lambda x, y: x+y, [1,2,3,4])  # 10",
            "",
            "double = functools.partial(pow, exp=2)   # partial application",
            "double(5)  # 25",
            "",
            "@functools.wraps(func)  # preserve docstring in decorators",
        ],
    },
    "threading": {
        "import": "import threading",
        "examples": [
            "t = threading.Thread(target=my_func, args=(arg1,))",
            "t.daemon = True   # dies with main thread",
            "t.start()         # launch",
            "t.join()          # wait for finish",
            "lock = threading.Lock()",
            "with lock:        # auto-release on scope exit",
            "    shared_var += 1",
            "event = threading.Event()",
            "event.set()  event.wait()  event.clear()",
        ],
    },
    "asyncio": {
        "import": "import asyncio",
        "examples": [
            "async def fetch(url):",
            "    await asyncio.sleep(1)   # non-blocking wait",
            "    return 'data'",
            "",
            "asyncio.run(fetch('http://example.com'))  # run one coroutine",
            "",
            "async def main():",
            "    results = await asyncio.gather(fetch(u1), fetch(u2))",
            "",
            "task = asyncio.create_task(fetch(url))  # fire and forget",
        ],
    },
    "flask": {
        "import": "from flask import Flask, request, jsonify, render_template",
        "examples": [
            "app = Flask(__name__)",
            "",
            "@app.route('/')",
            "def index(): return 'Hello World'",
            "",
            "@app.route('/api', methods=['GET', 'POST'])",
            "def api():",
            "    data = request.json   # POST body",
            "    return jsonify({'status': 'ok'})",
            "",
            "if __name__ == '__main__': app.run(debug=True, port=5000)",
        ],
    },
    "fastapi": {
        "import": "from fastapi import FastAPI\nfrom pydantic import BaseModel",
        "examples": [
            "app = FastAPI()",
            "",
            "@app.get('/')",
            "def root(): return {'message': 'Hello'}",
            "",
            "class Item(BaseModel):",
            "    name: str",
            "    price: float",
            "",
            "@app.post('/items')",
            "def create(item: Item): return item",
            "",
            "# Run: uvicorn main:app --reload",
        ],
    },
    "subprocess": {
        "import": "import subprocess",
        "examples": [
            "r = subprocess.run(['ls', '-la'], capture_output=True, text=True)",
            "r.stdout          # output string",
            "r.returncode      # 0 = success",
            "r.raise_for_status()  # raises on non-zero",
            "out = subprocess.check_output(['git', 'log'], text=True)",
            "subprocess.run('echo hello', shell=True, check=True)",
        ],
    },
    "argparse": {
        "import": "import argparse",
        "examples": [
            "parser = argparse.ArgumentParser(description='My tool')",
            "parser.add_argument('name')                  # positional",
            "parser.add_argument('--count', type=int, default=1)",
            "parser.add_argument('--verbose', '-v', action='store_true')",
            "parser.add_argument('--out', choices=['json', 'csv'])",
            "args = parser.parse_args()",
            "print(args.name, args.count, args.verbose)",
        ],
    },
    "logging": {
        "import": "import logging",
        "examples": [
            "logging.basicConfig(level=logging.INFO,",
            "    format='%(asctime)s %(levelname)s %(message)s')",
            "logging.debug('detail')    # only shown at DEBUG level",
            "logging.info('started')",
            "logging.warning('low disk')",
            "logging.error('failed')",
            "logging.exception('crash') # includes traceback",
            "logger = logging.getLogger(__name__)",
            "logger.info('from module')",
        ],
    },
    "math": {
        "import": "import math",
        "examples": [
            "math.sqrt(16)      # 4.0",
            "math.pow(2, 10)    # 1024.0",
            "math.floor(3.7)    # 3   math.ceil(3.2)  # 4",
            "math.log(100, 10)  # 2.0   math.log2(8)  # 3.0",
            "math.pi            # 3.14159...   math.e  # 2.71828...",
            "math.factorial(5)  # 120",
            "math.gcd(12, 8)    # 4",
            "math.inf           # infinity   math.isnan(x)  # check NaN",
        ],
    },
    "random": {
        "import": "import random",
        "examples": [
            "random.random()              # float in [0.0, 1.0)",
            "random.randint(1, 10)        # int in [1, 10]",
            "random.choice([1, 2, 3, 4]) # pick one element",
            "random.choices([1,2,3], weights=[1,2,1], k=5)",
            "random.shuffle(my_list)      # shuffle in place",
            "random.sample([1,2,3,4,5], 3)  # 3 unique picks",
            "random.seed(42)              # reproducible results",
        ],
    },
    "time": {
        "import": "import time",
        "examples": [
            "time.time()                  # seconds since epoch (float)",
            "time.sleep(1.5)              # sleep 1.5 seconds",
            "start = time.perf_counter()  # high-resolution timer",
            "# ... work ...",
            "elapsed = time.perf_counter() - start",
            "time.strftime('%Y-%m-%d %H:%M:%S')  # formatted time string",
        ],
    },
    "csv": {
        "import": "import csv",
        "examples": [
            "with open('data.csv') as f:",
            "    reader = csv.DictReader(f)",
            "    for row in reader:",
            "        print(row['name'], row['age'])",
            "",
            "with open('out.csv', 'w', newline='') as f:",
            "    writer = csv.DictWriter(f, fieldnames=['name', 'age'])",
            "    writer.writeheader()",
            "    writer.writerow({'name': 'Alice', 'age': 30})",
        ],
    },
    "shutil": {
        "import": "import shutil",
        "examples": [
            "shutil.copy('src.txt', 'dst.txt')        # copy file",
            "shutil.copytree('src_dir', 'dst_dir')    # copy directory",
            "shutil.move('old_path', 'new_path')      # move/rename",
            "shutil.rmtree('dir_to_delete')           # delete directory tree",
            "shutil.make_archive('backup', 'zip', 'folder/')",
            "shutil.unpack_archive('backup.zip', 'out/')",
        ],
    },
    "typing": {
        "import": "from typing import List, Dict, Optional, Tuple, Union, Any, Callable",
        "examples": [
            "def greet(name: str) -> str:",
            "    return f'Hello {name}'",
            "",
            "def process(items: List[int]) -> Dict[str, int]:",
            "    return {'sum': sum(items)}",
            "",
            "def find(x: Optional[int] = None) -> Optional[str]:",
            "    return str(x) if x is not None else None",
            "",
            "# Python 3.10+: use X | Y instead of Union[X, Y]",
        ],
    },
    "pydantic": {
        "import": "from pydantic import BaseModel, Field",
        "examples": [
            "class User(BaseModel):",
            "    name: str",
            "    age: int",
            "    email: str = Field(..., pattern=r'.+@.+')",
            "",
            "u = User(name='Alice', age=30, email='a@b.com')",
            "u.model_dump()        # -> dict",
            "u.model_json_schema() # JSON schema",
        ],
    },
    "sklearn": {
        "import": "from sklearn.model_selection import train_test_split\nfrom sklearn.preprocessing import StandardScaler",
        "examples": [
            "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)",
            "scaler = StandardScaler()",
            "X_train = scaler.fit_transform(X_train)",
            "X_test  = scaler.transform(X_test)",
            "from sklearn.ensemble import RandomForestClassifier",
            "clf = RandomForestClassifier(n_estimators=100)",
            "clf.fit(X_train, y_train)",
            "clf.predict(X_test)",
            "clf.score(X_test, y_test)  # accuracy",
        ],
    },
    "torch": {
        "import": "import torch\nimport torch.nn as nn",
        "examples": [
            "t = torch.tensor([1.0, 2.0, 3.0])",
            "torch.zeros(3, 4)  torch.ones(3, 4)  torch.randn(3, 4)",
            "t.shape  t.dtype  t.device",
            "t.to('cuda')       # move to GPU",
            "t.numpy()          # to NumPy (CPU only)",
            "model = nn.Sequential(nn.Linear(10, 64), nn.ReLU(), nn.Linear(64, 1))",
            "loss_fn = nn.MSELoss()",
            "optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)",
        ],
    },
    "sqlalchemy": {
        "import": "from sqlalchemy import create_engine, Column, Integer, String\nfrom sqlalchemy.orm import declarative_base, Session",
        "examples": [
            "engine = create_engine('sqlite:///db.sqlite3')",
            "Base = declarative_base()",
            "class User(Base):",
            "    __tablename__ = 'users'",
            "    id   = Column(Integer, primary_key=True)",
            "    name = Column(String)",
            "Base.metadata.create_all(engine)",
            "with Session(engine) as s:",
            "    s.add(User(name='Alice'))  s.commit()",
            "    users = s.query(User).filter_by(name='Alice').all()",
        ],
    },
    "socket": {
        "import": "import socket",
        "examples": [
            "# TCP client",
            "with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:",
            "    s.connect(('localhost', 8080))",
            "    s.sendall(b'Hello')",
            "    data = s.recv(1024)",
            "# TCP server",
            "with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:",
            "    s.bind(('', 8080))  s.listen()",
            "    conn, addr = s.accept()",
            "    with conn: data = conn.recv(1024)",
            "socket.gethostname()",
            "socket.gethostbyname('example.com')",
        ],
    },
    "hashlib": {
        "import": "import hashlib",
        "examples": [
            "h = hashlib.sha256('hello'.encode())",
            "h.hexdigest()      # hex string of hash",
            "hashlib.md5(b'data').hexdigest()",
            "# Hash a file",
            "h = hashlib.sha256()",
            "with open('file.bin', 'rb') as f:",
            "    for chunk in iter(lambda: f.read(4096), b''):",
            "        h.update(chunk)",
            "h.hexdigest()",
        ],
    },
    "copy": {
        "import": "import copy",
        "examples": [
            "a = [[1, 2], [3, 4]]",
            "b = copy.copy(a)       # shallow -- nested lists still shared",
            "b[0].append(99)        # also modifies a[0]!",
            "c = copy.deepcopy(a)   # fully independent",
            "c[0].append(99)        # does NOT affect a",
        ],
    },
    "contextlib": {
        "import": "from contextlib import contextmanager, suppress",
        "examples": [
            "@contextmanager",
            "def managed():",
            "    resource = acquire()",
            "    try:",
            "        yield resource",
            "    finally:",
            "        release(resource)",
            "",
            "with managed() as r: use(r)",
            "",
            "with suppress(FileNotFoundError):  # swallow specific error",
            "    os.remove('maybe_missing.txt')",
        ],
    },
    "abc": {
        "import": "from abc import ABC, abstractmethod",
        "examples": [
            "class Shape(ABC):",
            "    @abstractmethod",
            "    def area(self) -> float: ...",
            "",
            "class Circle(Shape):",
            "    def __init__(self, r): self.r = r",
            "    def area(self): return 3.14159 * self.r ** 2",
            "",
            "# Shape()  # TypeError -- can't instantiate abstract class",
            "Circle(5).area()  # works",
        ],
    },
    "string": {
        "import": "import string",
        "examples": [
            "string.ascii_letters    # 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'",
            "string.ascii_lowercase  # 'abcdefghijklmnopqrstuvwxyz'",
            "string.ascii_uppercase  # 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'",
            "string.digits           # '0123456789'",
            "string.hexdigits        # '0123456789abcdefABCDEF'",
            "string.punctuation      # all punctuation chars",
            "string.whitespace       # ' \\t\\n\\r\\x0b\\x0c'",
            "# Template substitution",
            "t = string.Template('Hello $name, you are $age years old!')",
            "t.substitute(name='Alice', age=30)   # fills all placeholders",
            "t.safe_substitute(name='Alice')      # leaves missing ones as-is",
            "# Build a random password",
            "import random",
            "chars = string.ascii_letters + string.digits + string.punctuation",
            "''.join(random.choices(chars, k=16))   # 16-char random password",
        ],
    },
    "heapq": {
        "import": "import heapq",
        "examples": [
            "h = []",
            "heapq.heappush(h, 5)   # push item",
            "heapq.heappush(h, 1)",
            "heapq.heappush(h, 3)",
            "heapq.heappop(h)       # 1  (smallest first -- min-heap)",
            "h[0]                   # peek without popping",
            "# Build from existing list",
            "data = [5, 1, 3, 2, 4]",
            "heapq.heapify(data)    # convert list to heap in-place O(n)",
            "# N smallest / largest",
            "heapq.nsmallest(3, data)   # [1, 2, 3]",
            "heapq.nlargest(3, data)    # [5, 4, 3]",
            "# Max-heap trick: push negative values",
            "heapq.heappush(h, -priority)",
            "priority = -heapq.heappop(h)",
        ],
    },
    "bisect": {
        "import": "import bisect",
        "examples": [
            "data = [1, 3, 5, 7, 9]  # must be sorted",
            "bisect.bisect_left(data, 5)   # 2  (index where 5 would go, left)",
            "bisect.bisect_right(data, 5)  # 3  (index after 5)",
            "bisect.insort(data, 6)        # insert 6 keeping sorted order",
            "# Typical use: grade lookup",
            "breakpoints = [60, 70, 80, 90]",
            "grades = 'FDCBA'",
            "def grade(score): return grades[bisect.bisect(breakpoints, score)]",
            "grade(85)  # 'B'",
        ],
    },
    "dataclasses": {
        "import": "from dataclasses import dataclass, field",
        "examples": [
            "@dataclass",
            "class Point:",
            "    x: float",
            "    y: float",
            "    z: float = 0.0   # default value",
            "",
            "p = Point(1.0, 2.0)",
            "p.x  p.y  p.z",
            "# With mutable default (must use field)",
            "@dataclass",
            "class Config:",
            "    tags: list = field(default_factory=list)",
            "    name: str = 'default'",
            "",
            "# frozen=True makes it immutable (hashable)",
            "@dataclass(frozen=True)",
            "class Vector:",
            "    x: float; y: float",
        ],
    },
    "enum": {
        "import": "from enum import Enum, IntEnum, auto",
        "examples": [
            "class Color(Enum):",
            "    RED   = 1",
            "    GREEN = 2",
            "    BLUE  = 3",
            "",
            "Color.RED            # <Color.RED: 1>",
            "Color.RED.name       # 'RED'",
            "Color.RED.value      # 1",
            "Color(1)             # <Color.RED: 1>  -- lookup by value",
            "Color['RED']         # lookup by name",
            "list(Color)          # all members",
            "# auto() assigns values automatically",
            "class Status(Enum):",
            "    PENDING = auto()   # 1",
            "    ACTIVE  = auto()   # 2",
            "    DONE    = auto()   # 3",
        ],
    },
    "io": {
        "import": "import io",
        "examples": [
            "# In-memory text buffer (like an open file)",
            "buf = io.StringIO()",
            "buf.write('hello')  buf.write(' world')",
            "buf.getvalue()          # 'hello world'",
            "buf.seek(0)             # rewind",
            "buf.read()              # 'hello world'",
            "# In-memory bytes buffer",
            "bbuf = io.BytesIO(b'hello')",
            "bbuf.read(3)            # b'hel'",
            "bbuf.seek(0)",
            "# Wrap a raw stream with buffering",
            "with open('file.bin', 'rb') as raw:",
            "    wrapped = io.BufferedReader(raw)",
        ],
    },
    "struct": {
        "import": "import struct",
        "examples": [
            "# Pack integers into binary bytes",
            "data = struct.pack('>IH', 1024, 5)  # big-endian uint32 + uint16",
            "len(data)   # 6 bytes",
            "# Unpack binary bytes back to Python values",
            "struct.unpack('>IH', data)  # (1024, 5)",
            "# Format characters: b=int8 B=uint8 h=int16 H=uint16",
            "#   i=int32 I=uint32 q=int64 Q=uint64 f=float d=double",
            "#   > big-endian  < little-endian  = native",
            "struct.calcsize('>IH')   # 6  -- bytes needed",
            "# Struct object for repeated use",
            "fmt = struct.Struct('<4B')  # 4 little-endian bytes",
            "fmt.pack(10, 20, 30, 40)",
        ],
    },
    "pickle": {
        "import": "import pickle",
        "examples": [
            "data = {'name': 'Alice', 'scores': [95, 87, 92]}",
            "# Save to file",
            "with open('data.pkl', 'wb') as f:",
            "    pickle.dump(data, f)",
            "# Load from file",
            "with open('data.pkl', 'rb') as f:",
            "    loaded = pickle.load(f)",
            "# Serialize to bytes (in-memory)",
            "blob = pickle.dumps(data)",
            "obj  = pickle.loads(blob)",
            "# WARNING: never unpickle data from untrusted sources",
        ],
    },
    "sqlite3": {
        "import": "import sqlite3",
        "examples": [
            "conn = sqlite3.connect('mydb.sqlite3')  # or ':memory:'",
            "cur  = conn.cursor()",
            "cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)')",
            "cur.execute('INSERT INTO users (name) VALUES (?)', ('Alice',))",
            "conn.commit()",
            "cur.execute('SELECT * FROM users WHERE name = ?', ('Alice',))",
            "cur.fetchall()        # list of tuples",
            "cur.fetchone()        # one tuple or None",
            "conn.row_factory = sqlite3.Row  # access columns by name",
            "conn.close()",
            "# Context manager (auto-commits or rolls back)",
            "with sqlite3.connect('mydb.sqlite3') as conn:",
            "    conn.execute('INSERT INTO users (name) VALUES (?)', ('Bob',))",
        ],
    },
    "glob": {
        "import": "import glob",
        "examples": [
            "glob.glob('*.py')              # all .py files in cwd",
            "glob.glob('src/**/*.py', recursive=True)  # recursive",
            "glob.glob('/tmp/*.log')        # absolute path pattern",
            "# glob.glob returns a list -- use iglob for an iterator",
            "for path in glob.iglob('data/**/*.csv', recursive=True):",
            "    print(path)",
        ],
    },
    "tempfile": {
        "import": "import tempfile",
        "examples": [
            "# Temporary file (deleted when closed)",
            "with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:",
            "    f.write('hello')  f.name  # e.g. /tmp/tmpXXXXXX.txt",
            "# Temporary directory (deleted on exit)",
            "with tempfile.TemporaryDirectory() as tmpdir:",
            "    path = tmpdir + '/file.txt'   # use any path inside",
            "# Get system temp directory",
            "tempfile.gettempdir()   # '/tmp' on Linux, 'C:\\\\Temp' on Windows",
        ],
    },
    "queue": {
        "import": "from queue import Queue, LifoQueue, PriorityQueue",
        "examples": [
            "# Thread-safe FIFO queue",
            "q = Queue(maxsize=0)   # 0 = unlimited",
            "q.put('task1')",
            "q.put('task2')",
            "item = q.get()         # 'task1'  (blocks if empty)",
            "q.task_done()          # signal that item is processed",
            "q.join()               # block until all items processed",
            "# LIFO (stack)",
            "lq = LifoQueue()",
            "lq.put(1)  lq.put(2)  lq.get()  # 2",
            "# Priority queue (smallest first)",
            "pq = PriorityQueue()",
            "pq.put((2, 'low'))  pq.put((1, 'high'))",
            "pq.get()  # (1, 'high')",
        ],
    },
    "unittest": {
        "import": "import unittest",
        "examples": [
            "class TestMath(unittest.TestCase):",
            "    def test_add(self):",
            "        self.assertEqual(1 + 1, 2)",
            "    def test_raises(self):",
            "        with self.assertRaises(ZeroDivisionError):",
            "            1 / 0",
            "    def test_approx(self):",
            "        self.assertAlmostEqual(0.1 + 0.2, 0.3, places=5)",
            "    def setUp(self):    # runs before each test",
            "        self.db = connect()",
            "    def tearDown(self): # runs after each test",
            "        self.db.close()",
            "",
            "if __name__ == '__main__': unittest.main()",
            "# Run: python -m pytest  or  python -m unittest",
        ],
    },
    "urllib": {
        "import": "from urllib import request, parse, error",
        "examples": [
            "# Simple GET request",
            "with request.urlopen('https://example.com') as r:",
            "    html = r.read().decode('utf-8')",
            "    r.status  r.headers['Content-Type']",
            "# URL encoding",
            "parse.urlencode({'q': 'hello world', 'page': 1})  # 'q=hello+world&page=1'",
            "parse.quote('hello world')    # 'hello%20world'",
            "parse.unquote('hello%20world')  # 'hello world'",
            "parse.urlparse('https://example.com/path?q=1')",
            "# -> ParseResult(scheme='https', netloc='example.com', ...)",
        ],
    },
    "concurrent": {
        "import": "from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor",
        "examples": [
            "def task(n): return n * n",
            "",
            "# Thread pool (I/O-bound work)",
            "with ThreadPoolExecutor(max_workers=4) as ex:",
            "    results = list(ex.map(task, range(10)))",
            "    future  = ex.submit(task, 5)",
            "    future.result()   # 25  (blocks until done)",
            "",
            "# Process pool (CPU-bound work)",
            "with ProcessPoolExecutor(max_workers=4) as ex:",
            "    results = list(ex.map(task, range(10)))",
        ],
    },
    "multiprocessing": {
        "import": "import multiprocessing as mp",
        "examples": [
            "def worker(x): return x * x",
            "",
            "# Process pool",
            "with mp.Pool(processes=4) as pool:",
            "    results = pool.map(worker, range(10))",
            "",
            "# Single process",
            "p = mp.Process(target=worker, args=(5,))",
            "p.start()  p.join()",
            "# Shared memory",
            "counter = mp.Value('i', 0)  # shared int",
            "arr     = mp.Array('d', [1.0, 2.0, 3.0])  # shared double array",
            "# Queue between processes",
            "q = mp.Queue()",
            "q.put('data')  q.get()",
        ],
    },
    "traceback": {
        "import": "import traceback",
        "examples": [
            "try:",
            "    risky_call()",
            "except Exception as e:",
            "    traceback.print_exc()            # print to stderr",
            "    msg = traceback.format_exc()     # get as string",
            "    lines = traceback.extract_tb(e.__traceback__)",
            "# Print just the last frame",
            "traceback.print_last()",
            "# Format a specific exception",
            "traceback.format_exception(type(e), e, e.__traceback__)",
        ],
    },
    "warnings": {
        "import": "import warnings",
        "examples": [
            "warnings.warn('deprecated, use new_func()', DeprecationWarning)",
            "warnings.warn('low memory', ResourceWarning, stacklevel=2)",
            "# Suppress specific warnings",
            "with warnings.catch_warnings():",
            "    warnings.simplefilter('ignore', DeprecationWarning)",
            "    old_function()",
            "# Turn warnings into errors",
            "warnings.filterwarnings('error', category=DeprecationWarning)",
        ],
    },
}

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

_PY_HINTS = ('import ', 'from ', 'def ', 'class ', 'print(', 'return ',
             'if __name__', '>>>', ' = ', '.append(', '.get(', 'async ')


def _looks_like_python(code: str) -> bool:
    return any(h in code for h in _PY_HINTS)


def _extract_code_blocks(desc: str) -> list:
    """Pull Python code examples out of a markdown or RST description."""
    blocks: list = []

    # 1. Fenced blocks explicitly tagged as python / py / pycon / python3
    for m in re.finditer(
        r'```[ \t]*(?:python3?|py|pycon|py3)\n(.*?)```',
        desc, re.DOTALL | re.IGNORECASE
    ):
        code = m.group(1).strip()
        if len(code) > 20:
            blocks.append(code)
        if len(blocks) >= 3:
            break

    if blocks:
        return blocks

    # 2. Untagged fenced blocks that look like Python code
    for m in re.finditer(r'```\n(.*?)```', desc, re.DOTALL):
        code = m.group(1).strip()
        if len(code) > 20 and _looks_like_python(code):
            blocks.append(code)
        if len(blocks) >= 3:
            break

    if blocks:
        return blocks

    # 3. RST  .. code-block:: python  or bare ::
    for m in re.finditer(
        r'(?:code-block::\s*python|::)\s*\n\n((?:[ \t]+.+\n?)+)',
        desc, re.IGNORECASE
    ):
        lines  = m.group(1).splitlines()
        indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        code   = "\n".join(l[indent:] for l in lines).strip()
        if len(code) > 20 and _looks_like_python(code):
            blocks.append(code)
        if len(blocks) >= 3:
            break

    return blocks


def _print_python_quickstart(name: str, desc: str = ""):
    """Print import line + usage examples. Always runs first."""
    key = name.lower()
    qs  = _PYTHON_QUICKSTART.get(key)

    if qs:
        imp_line     = qs["import"]
        dict_examples = qs["examples"]
        raw_blocks   = []
    else:
        imp_line     = f"import {key}"
        dict_examples = []
        raw_blocks   = _extract_code_blocks(desc) if desc else []

    console.print(f"\n[bold yellow]Import:[/bold yellow]")
    if RICH:
        console.print(Syntax(imp_line, "python", theme="monokai"))
    else:
        for ln in imp_line.splitlines():
            console.print(f"  {ln}")

    if dict_examples:
        console.print(f"\n[bold yellow]Quick start:[/bold yellow]")
        block = "\n".join(dict_examples)
        if RICH:
            console.print(Syntax(block, "python", theme="monokai"))
        else:
            for ln in dict_examples:
                console.print(f"  {ln}" if ln else "")

    elif raw_blocks:
        console.print(f"\n[bold yellow]Examples from README:[/bold yellow]")
        for i, block in enumerate(raw_blocks):
            # strip >>> / ... prompts so the block is copy-paste ready
            clean_lines = []
            for ln in block.splitlines():
                s = ln.lstrip()
                if s.startswith('>>> '):
                    clean_lines.append(ln.replace('>>> ', '', 1))
                elif s.startswith('... '):
                    clean_lines.append(ln.replace('... ', '', 1))
                elif s == '>>>' or s == '...':
                    clean_lines.append('')
                else:
                    clean_lines.append(ln)
            clean = "\n".join(clean_lines).strip()
            if RICH:
                console.print(Syntax(clean, "python", theme="monokai"))
            else:
                for ln in clean.splitlines():
                    console.print(f"  {ln}")
            if i < len(raw_blocks) - 1:
                console.print()

    # For any package not in the hand-crafted dict, always ask Ollama too.
    # This runs after README examples (if any) so the AI adds real-world context
    # on top of what the README already shows.
    if not dict_examples:
        ok, model = _ollama_available()
        if ok:
            console.print(f"\n[dim]  asking {model} for examples...[/dim]")
            prompt = (
                f"You are a Python expert. Show me exactly how to use the Python library or module '{name}'.\n"
                f"Output ONLY Python code (no prose outside of # comments).\n"
                f"Include:\n"
                f"1. The correct import statement(s)\n"
                f"2. 6-10 practical, real-world usage examples with short # comments\n"
                f"Cover the most commonly used features. Be concise. No markdown fences."
            )
            ai_code = _ollama_generate(prompt, model, timeout=90)
            if ai_code:
                ai_code = re.sub(r'^```[a-z]*\n?', '', ai_code, flags=re.MULTILINE)
                ai_code = re.sub(r'\n?```$', '', ai_code, flags=re.MULTILINE)
                ai_code = ai_code.strip()
                console.print(f"\n[bold yellow]Examples (AI - {model}):[/bold yellow]")
                if RICH:
                    console.print(Syntax(ai_code, "python", theme="monokai"))
                else:
                    for ln in ai_code.splitlines():
                        console.print(f"  {ln}")


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

        # -- always show import + examples first --
        _print_python_quickstart(name, desc=desc)

        if RICH:
            console.print(Panel(
                f"[bold white]{name}[/bold white]  [dim]v{ver}[/dim]\n\n{summary}",
                title="[bold green]PyPI Package[/bold green]", border_style="green"
            ))
        else:
            console.print(f"\n=== {name} v{ver} ===\n{summary}")

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
            console.print(f"\n[bold yellow]Description:[/bold yellow]")
            snippet = desc[:1500].encode("ascii", errors="replace").decode("ascii")
            console.print(snippet)
        return

    # fallback: stdlib via pydoc -- show quickstart first
    _print_python_quickstart(pkg)
    out = _pydoc(pkg)
    if out:
        # Extract only the description block (stop before CLASS / FUNCTIONS wall)
        stop_markers = ('\nCLASSES', '\nFUNCTIONS', '\nDATA', '\nFILE')
        snippet = out
        for marker in stop_markers:
            idx = snippet.find(marker)
            if idx != -1:
                snippet = snippet[:idx]
        snippet = snippet.strip()[:1200]
        if RICH:
            console.print(Panel(snippet,
                title=f"[bold green]Python stdlib | {pkg}[/bold green]", border_style="green"))
        else:
            console.print(snippet)

        console.print(f"\n[bold yellow]Full reference:[/bold yellow]")
        console.print(f"  https://docs.python.org/3/library/{pkg}.html")
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
#  ASK  (AI tech-stack advisor)
# ══════════════════════════════════════════════════════════════════════════════

def show_ask(question: str):
    """Describe what you want to build -- get back a recommended tech stack."""
    ok, model = _ollama_available()
    if not ok:
        console.print(f"\n[red]Ollama is not running.[/red]")
        console.print("  Start it:      ollama serve")
        console.print("  Install model: ollama pull gemma4")
        return

    console.print(f"\n[bold cyan]Tech-stack advisor[/bold cyan]  "
                  f"[dim]({model})[/dim]\n")
    console.print(f"[dim]  thinking...[/dim]\n")

    prompt = f"""You are a senior software engineer advising a developer.
They want to build: {question}

Give a focused, practical answer in this exact structure:

## What to use
- <library>  --  <one-line reason>
(list every library/module/tool they need, nothing extra)

## Install
pip install <all packages on one line>

## Minimal example
A short but complete working code snippet showing how the key pieces fit together.
Use real imports. Add brief # comments on important lines.

## When to use each
One sentence per library on the best use-case or gotcha a pro would want to know.

No marketing language. Be direct. Output plain text + code blocks only."""

    response = _ollama_generate(prompt, model, timeout=90)
    if not response:
        console.print("[red]No response from LLM.[/red]")
        return

    # clean stray markdown fences around the whole reply
    response = response.strip()
    console.print(response)


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

    ak  = sub.add_parser("ask",     aliases=["a"],           help="AI tech-stack advisor (needs Ollama)")
    ak.add_argument("question", nargs="+",
                    help="Describe what you want to build, e.g. 'a REST API with auth and database'")

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
    elif args.cmd in ("ask", "a"):
        show_ask(" ".join(args.question))
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
            "[cyan]ask[/cyan]    [white]<what>[/white]    AI tech-stack advisor  (needs Ollama)\n"
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
        elif cmd in ("ask", "a"):
            if rest:
                show_ask(rest)
            else:
                console.print("[red]Usage:  ask <describe what you want to build>[/red]")
        elif cmd in ("help", "h", "?"):
            console.print(
                "[cyan]python[/cyan] <pkg>  |  [cyan]linux[/cyan] <cmd>  |  "
                "[cyan]cpp[/cyan] <topic>  |  [cyan]search[/cyan] <term>  |  "
                "[cyan]ask[/cyan] <what to build>  |  [cyan]list[/cyan]  |  [cyan]q[/cyan]"
            )
        else:
            # try auto-detect: single word -> search all
            console.print(f"[dim]Searching all languages for '{raw}'...[/dim]")
            show_search(raw)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
DocPilot GUI -- floating documentation window
Runs alongside VS Code or Jupyter. Pin it to the side and search while coding.

Launch:  python gui.py
         (or double-click launch.bat on Windows)
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import re
import threading
import os

# path to docpilot.py (same folder as this file)
DOCPILOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docpilot.py')

# ── VS Code dark theme colors ──────────────────────────────────────────────────
BG      = '#1e1e1e'
BG2     = '#252526'
BG3     = '#2d2d2d'
FG      = '#d4d4d4'
ACCENT  = '#007acc'
GREEN   = '#4ec9b0'
YELLOW  = '#dcdcaa'
RED     = '#f44747'
BORDER  = '#3c3c3c'
DIM     = '#6a6a6a'

FONT      = ('Consolas', 11)
FONT_SM   = ('Consolas', 10)
FONT_BOLD = ('Consolas', 11, 'bold')


def strip_ansi(text):
    """Remove ANSI color codes so terminal output displays cleanly in the GUI."""
    return re.sub(r'\x1b\[[0-9;]*[mKJH]', '', text)


# ── main window ────────────────────────────────────────────────────────────────

class DocPilotApp(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("DocPilot")
        self.geometry("640x720+40+40")   # width x height + x_offset + y_offset
        self.minsize(500, 400)
        self.configure(bg=BG)

        # float on top of VS Code by default
        self.attributes('-topmost', True)

        self._build_ui()
        self._bind_keys()

        # greet
        self._set_text(WELCOME)
        self.search_entry.focus_set()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):

        # ── top bar ───────────────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=BG2, pady=8, padx=14)
        topbar.pack(fill='x')

        tk.Label(topbar, text="DocPilot", font=('Consolas', 13, 'bold'),
                 bg=BG2, fg=ACCENT).pack(side='left')

        tk.Label(topbar, text="  Python · Linux · C++",
                 font=FONT_SM, bg=BG2, fg=DIM).pack(side='left')

        # pin toggle -- keeps window on top of VS Code
        self.pin_var = tk.BooleanVar(value=True)
        pin_cb = tk.Checkbutton(topbar, text="📌 pin", variable=self.pin_var,
                                command=self._toggle_pin,
                                bg=BG2, fg=DIM, selectcolor=BG2,
                                activebackground=BG2, activeforeground=FG,
                                font=FONT_SM, cursor='hand2')
        pin_cb.pack(side='right')

        # ── search row ────────────────────────────────────────────────────────
        search_frame = tk.Frame(self, bg=BG, padx=14, pady=10)
        search_frame.pack(fill='x')

        self.lang_var = tk.StringVar(value='python')
        lang_drop = ttk.Combobox(search_frame, textvariable=self.lang_var,
                                 values=['python', 'linux', 'cpp', 'search'],
                                 state='readonly', width=9, font=FONT)
        lang_drop.pack(side='left', padx=(0, 8))

        self.search_entry = tk.Entry(search_frame, font=FONT,
                                     bg=BG3, fg=FG,
                                     insertbackground=FG,
                                     relief='flat',
                                     highlightthickness=1,
                                     highlightcolor=ACCENT,
                                     highlightbackground=BORDER)
        self.search_entry.pack(side='left', fill='x', expand=True, ipady=6)

        self.go_btn = tk.Button(search_frame, text='Go', font=FONT_SM,
                                bg=ACCENT, fg='white', relief='flat',
                                padx=14, cursor='hand2',
                                activebackground='#005999',
                                command=self._run_search)
        self.go_btn.pack(side='left', padx=(8, 0))

        # ── quick example buttons ─────────────────────────────────────────────
        pills = tk.Frame(self, bg=BG, padx=14)
        pills.pack(fill='x')

        tk.Label(pills, text="try: ", bg=BG, fg=DIM, font=FONT_SM).pack(side='left')

        examples = [
            ('numpy',      'python', 'numpy'),
            ('os',         'python', 'os'),
            ('grep',       'linux',  'grep'),
            ('curl',       'linux',  'curl'),
            ('vector',     'cpp',    'vector'),
            ('sort',       'cpp',    'sort'),
            ('unique_ptr', 'cpp',    'unique_ptr'),
        ]
        for label, lang, query in examples:
            b = tk.Button(pills, text=label, font=('Consolas', 9),
                          bg=BG2, fg='#888', relief='flat', padx=6,
                          cursor='hand2', activebackground=BORDER,
                          activeforeground=FG,
                          command=lambda l=lang, q=query: self._quick(l, q))
            b.pack(side='left', padx=2, pady=4)

        # separator line
        tk.Frame(self, bg=BORDER, height=1).pack(fill='x', padx=14)

        # ── results text box ──────────────────────────────────────────────────
        result_frame = tk.Frame(self, bg=BG, padx=14, pady=8)
        result_frame.pack(fill='both', expand=True)

        self.textbox = tk.Text(result_frame,
                               font=('Consolas', 10),
                               bg=BG2, fg=FG,
                               relief='flat', wrap='word',
                               state='disabled',
                               padx=12, pady=10,
                               spacing1=2, spacing3=2,
                               selectbackground=ACCENT,
                               insertbackground=FG,
                               cursor='arrow')

        scrollbar = tk.Scrollbar(result_frame, orient='vertical',
                                 command=self.textbox.yview,
                                 bg=BG, troughcolor=BG2,
                                 activebackground=DIM)
        self.textbox.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side='right', fill='y')
        self.textbox.pack(fill='both', expand=True)

        # color tags for different parts of the output
        self.textbox.tag_config('heading', foreground=ACCENT,
                                font=('Consolas', 11, 'bold'))
        self.textbox.tag_config('code',    foreground=GREEN,
                                font=('Consolas', 10))
        self.textbox.tag_config('url',     foreground='#569cd6')
        self.textbox.tag_config('label',   foreground=YELLOW)
        self.textbox.tag_config('dim',     foreground=DIM)
        self.textbox.tag_config('normal',  foreground=FG)
        self.textbox.tag_config('error',   foreground=RED)

        # ── status bar ────────────────────────────────────────────────────────
        self.statusbar = tk.Label(self,
                                  text="  Enter to search  |  Ctrl+L to clear  |  Esc to minimise",
                                  bg=BG2, fg=DIM,
                                  font=('Consolas', 9),
                                  anchor='w', padx=14, pady=4)
        self.statusbar.pack(fill='x', side='bottom')

    # ── interaction ────────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.search_entry.bind('<Return>',    lambda e: self._run_search())
        self.search_entry.bind('<KP_Enter>',  lambda e: self._run_search())
        self.bind('<Control-l>',              lambda e: self._clear_search())
        self.bind('<Escape>',                 lambda e: self.iconify())

    def _toggle_pin(self):
        self.attributes('-topmost', self.pin_var.get())

    def _clear_search(self):
        self.search_entry.delete(0, 'end')
        self.search_entry.focus_set()

    def _quick(self, lang, query):
        """Fill in the search box and immediately search."""
        self.lang_var.set(lang)
        self.search_entry.delete(0, 'end')
        self.search_entry.insert(0, query)
        self._run_search()

    # ── search ─────────────────────────────────────────────────────────────────

    def _run_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        lang = self.lang_var.get()
        self.statusbar.configure(text=f"  searching {lang}: {query} ...")
        self.go_btn.configure(state='disabled', text='...')
        self._set_text("  fetching docs...")

        def worker():
            try:
                result = subprocess.run(
                    [sys.executable, DOCPILOT, lang, query],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=15
                )
                raw = result.stdout or result.stderr or "no output returned"
                text = strip_ansi(raw)
            except subprocess.TimeoutExpired:
                text = "  timed out -- check your internet connection"
            except FileNotFoundError:
                text = f"  could not find docpilot.py at:\n  {DOCPILOT}"
            except Exception as e:
                text = f"  error: {e}"

            # always update the UI from the main thread
            self.after(0, lambda: self._set_text(text))
            self.after(0, lambda: self.statusbar.configure(
                text=f"  {lang}  |  {query}  "
                     f"|  Enter to search again  |  Ctrl+L to clear"
            ))
            self.after(0, lambda: self.go_btn.configure(state='normal', text='Go'))

        threading.Thread(target=worker, daemon=True).start()

    # ── rendering ──────────────────────────────────────────────────────────────

    def _set_text(self, text):
        """Write text into the result box with simple syntax coloring."""
        self.textbox.configure(state='normal')
        self.textbox.delete('1.0', 'end')

        in_code_block = False

        for line in text.splitlines():
            stripped = line.strip()

            # detect code block fences
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                self.textbox.insert('end', line + '\n', 'dim')
                continue

            if in_code_block:
                self.textbox.insert('end', line + '\n', 'code')
                continue

            # section headings  (lines starting with ##)
            if stripped.startswith('##') or stripped.startswith('==='):
                self.textbox.insert('end', line + '\n', 'heading')

            # URLs
            elif stripped.startswith('http') or 'https://' in stripped:
                self.textbox.insert('end', line + '\n', 'url')

            # install / include / reference lines
            elif any(stripped.startswith(k) for k in
                     ('pip install', '#include', 'Install:', 'Include:',
                      'Reference:', 'Links:', '  pip', '  #include')):
                self.textbox.insert('end', line + '\n', 'code')

            # indented code (likely a code example)
            elif line.startswith('   ') and stripped and \
                    not stripped.startswith('-') and \
                    not stripped.startswith('|'):
                self.textbox.insert('end', line + '\n', 'code')

            # table separators and dim lines
            elif stripped.startswith('---') or stripped.startswith('==='):
                self.textbox.insert('end', line + '\n', 'dim')

            # everything else
            else:
                self.textbox.insert('end', line + '\n', 'normal')

        self.textbox.configure(state='disabled')
        self.textbox.yview_moveto(0)   # scroll back to top


# ── welcome text ────────────────────────────────────────────────────────────────

WELCOME = """
  Welcome to DocPilot

  Search for any library, command, or function
  without leaving your editor.

  How to use:
    1. Pick a language from the dropdown
    2. Type the name of what you want
    3. Press Enter  (or click Go)

  Languages:
    python  --  any PyPI package or stdlib module
                e.g.  requests  |  numpy  |  os  |  json

    linux   --  any terminal command (TLDR examples)
                e.g.  grep  |  curl  |  awk  |  ssh

    cpp     --  C++ STL classes and algorithms
                e.g.  vector  |  sort  |  unique_ptr  |  map

    search  --  search across all three at once

  Keyboard shortcuts:
    Enter      run search
    Ctrl+L     clear search bar
    Esc        minimise window

  Click any of the quick buttons above to try an example.
"""


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = DocPilotApp()
    app.mainloop()

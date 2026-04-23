#!/usr/bin/env bash
# install.sh — sets up DocPilot and adds a shell alias

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet

ALIAS_LINE="alias docpilot='python \"$SCRIPT_DIR/docpilot.py\"'"

for RC in "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$RC" ]; then
        if grep -q "alias docpilot=" "$RC"; then
            sed -i "s|alias docpilot=.*|$ALIAS_LINE|" "$RC"
            echo "Updated alias in $RC"
        else
            echo "" >> "$RC"
            echo "# DocPilot — docs for Python / Linux / C++" >> "$RC"
            echo "$ALIAS_LINE" >> "$RC"
            echo "Alias added to $RC"
        fi
        break
    fi
done

echo ""
echo "Done! Restart your shell or run:"
echo "  source ~/.bashrc"
echo ""
echo "Then use:  docpilot python numpy"
echo "           docpilot linux grep"
echo "           docpilot cpp vector"
echo "           docpilot list"

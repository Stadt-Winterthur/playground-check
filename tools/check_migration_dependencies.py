#!/usr/bin/env python3
"""Report remaining legacy coupling without importing Django or touching the DB.

Exit with 1 only when --require-native is requested and coupling remains.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'src/playground_check/django_project'


def scan():
    findings = []
    for file in sorted(MODULES.glob('*.py')):
        tree = ast.parse(file.read_text(encoding='utf-8'))
        if file.name == 'legacy_adapter.py':
            continue  # Adapter definition, not a consumer.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if module == 'playground_check' and any(alias.name == 'service' for alias in node.names):
                    findings.append((file.name, node.lineno, 'playground_check.service'))
                elif module == 'legacy_adapter' and node.level == 1:
                    findings.append((file.name, node.lineno, 'legacy_adapter'))
                elif module in ('playground_check.service', 'playground_check.server'):
                    findings.append((file.name, node.lineno, module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ('playground_check.service', 'playground_check.server'):
                        findings.append((file.name, node.lineno, alias.name))
    return sorted(set(findings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-native', action='store_true', help='Fail if any remaining legacy imports are found')
    args = parser.parse_args()
    findings = scan()
    for file, line, dependency in findings:
        print(f'{file}:{line}: {dependency}')
    print(f'Remaining legacy dependency import sites: {len(findings)}')
    if args.require_native and findings:
        parser.exit(1, 'Native-only acceptance FAILED: legacy dependencies still present.\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Audit legacy HTTP route declarations against the method-aware DRF registry.

This is a static check: it does not import the application or connect to databases.
An explicit exemption is necessary for intentionally retained legacy-only routes.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'src/playground_check/server.py'
REGISTRY = ROOT / 'src/playground_check/django_project/route_registry.py'


def declared_legacy_routes():
    tree = ast.parse(SERVER.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != 'add' or len(node.args) < 2:
            continue
        try:
            method = ast.literal_eval(node.args[0])
            pattern = ast.literal_eval(node.args[1])
        except (ValueError, TypeError):
            continue
        if isinstance(method, str) and isinstance(pattern, str):
            yield method, pattern


def registry_routes():
    tree = ast.parse(REGISTRY.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ROUTES' for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError('ROUTES assignment missing')


def example_for(pattern):
    pattern = re.sub(r'\(\?P<[^>]+>\\d\+\)', '123', pattern)
    pattern = re.sub(r'\(\?P<[^>]+>\[\^/\]\+\)', 'sample', pattern)
    pattern = pattern.replace('/?', '')
    return pattern


def audit():
    routes = registry_routes()
    errors = []
    for method, legacy_pattern in declared_legacy_routes():
        sample = example_for(legacy_pattern)
        if '(?P<' in sample:
            errors.append(f'Cannot sample legacy route: {method} {legacy_pattern}')
            continue
        if not any(method in allowed.split() and re.fullmatch(pattern + r'/?', sample, re.IGNORECASE) for pattern, allowed, _ in routes):
            errors.append(f'Unmapped legacy API operation: {method} {legacy_pattern}')
    return errors


if __name__ == '__main__':
    problems = audit()
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f'Legacy API registry audit: {"FAILED" if problems else "OK"}')
    sys.exit(bool(problems))

#!/bin/sh
# Release gate: no deployment side effects and no production DB writes.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"

printf '\n== API coverage ==\n'
python tools/check_api_routes.py
printf '\n== Remaining legacy coupling (informational) ==\n'
python tools/check_migration_dependencies.py
printf '\n== Python compile check ==\n'
python -m compileall -q src/playground_check tests
if [ -n "${PLAYGROUND_TEST_POSTGRES_DSN:-}" ] && [ "${PLAYGROUND_TEST_DATABASE_CONFIRMED:-}" != 'isolated-test-only' ]; then
    printf '%s\n' 'REFUSED: integration DSN supplied without isolated-test-only confirmation.' >&2
    exit 2
fi
printf '\n== Full regression suite ==\n'
python -m unittest discover -s tests -v
printf '\n== Postgres integration ==\n'
if [ -z "${PLAYGROUND_TEST_POSTGRES_DSN:-}" ]; then
    printf '%s\n' 'SKIPPED: set PLAYGROUND_TEST_POSTGRES_DSN to an isolated, disposable TEST database and rerun.'
else
    if [ "${PLAYGROUND_TEST_DATABASE_CONFIRMED:-}" != "isolated-test-only" ]; then
        printf '%s\n' 'REFUSED: confirm an isolated nonproduction DB with PLAYGROUND_TEST_DATABASE_CONFIRMED=isolated-test-only.' >&2
        exit 2
    fi
    printf '%s\n' 'Dedicated integration DSN supplied; integration tests are included in the regression suite above.'
fi

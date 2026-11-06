"""Bounded CI readiness check; do not print DSNs or connection exceptions."""
import os
import time

import psycopg


def main() -> None:
    dsn = os.environ['PLAYGROUND_TEST_SESSION_DSN']
    deadline = time.monotonic() + 40
    while True:
        try:
            with psycopg.connect(dsn, connect_timeout=2) as connection:
                connection.execute('SELECT 1')
            print('Isolated PostgreSQL test database is ready.')
            return
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise SystemExit('PostgreSQL test database did not become ready.') from None
            time.sleep(1)


if __name__ == '__main__':
    main()

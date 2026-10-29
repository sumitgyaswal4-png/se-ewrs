"""One-time initialization of a hosted MySQL for SE-EWRS.

    cd backend
    python -m scripts.init_remote_db --admin-env ~/.config/se-ewrs/aiven.env \\
        --ca ~/.config/se-ewrs/aiven-ca.pem [--demo-data] [--probe-only]

``--admin-env`` is a KEY=value file, kept outside the repository, holding
the provider's admin connection: DB_ADMIN_HOST, DB_ADMIN_PORT,
DB_ADMIN_USER and DB_ADMIN_PASSWORD. ``--ca`` is the provider's CA
certificate; every connection verifies the server against it.

What it does, in order, stopping at the first problem:

1. Refuses to continue if ``se_ewrs`` already holds any table. schema.sql
   drops and recreates every table, so this never runs over real data.
2. Probes the server in a separate, throwaway ``se_ewrs_probe`` database
   for every feature the scripts need (triggers, stored functions and
   procedures, STORED generated columns, CHECK, foreign keys, CTEs, window
   functions), then drops that database. ``--probe-only`` stops here.
3. Loads schema, views, procedures, triggers and, with ``--demo-data``,
   seed.sql, over verified TLS, in the documented order.
4. With ``--demo-data``: gives every seeded account its own random
   password. The seed's shared password is published in the README, and on
   a public site it would let anyone sign in as an administrator.
5. Creates the least-privilege ``se_ewrs_app`` account the API connects as.

Every generated password is written to ``--out`` (mode 600, outside the
repository) and never printed.
"""

import argparse
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ["schema", "views", "procedures", "triggers"]
APP_USER = "se_ewrs_app"

PROBE = """
CREATE DATABASE se_ewrs_probe;
USE se_ewrs_probe;
CREATE TABLE parent (
    id INT PRIMARY KEY AUTO_INCREMENT,
    v INT NOT NULL CHECK (v >= 0),
    doubled INT AS (v * 2) STORED
);
CREATE TABLE child (
    id INT PRIMARY KEY,
    parent_id INT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES parent (id)
);
DELIMITER $$
CREATE FUNCTION f_det(x INT) RETURNS INT DETERMINISTIC RETURN x + 1$$
CREATE FUNCTION f_reads() RETURNS INT READS SQL DATA RETURN (SELECT COUNT(*) FROM parent)$$
CREATE PROCEDURE sp_probe() BEGIN SELECT f_det(1) + f_reads() AS r; END$$
CREATE TRIGGER trg_probe BEFORE INSERT ON parent FOR EACH ROW
BEGIN
    IF NEW.v > 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'probe trigger fired';
    END IF;
END$$
DELIMITER ;
CREATE VIEW v_probe AS
    WITH t AS (SELECT v FROM parent)
    SELECT v, ROW_NUMBER() OVER (ORDER BY v) AS rn FROM t;
INSERT INTO parent (v) VALUES (1);
INSERT INTO child (id, parent_id) VALUES (1, 1);
CALL sp_probe();
SELECT COUNT(*) FROM v_probe;
"""


def read_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Server:
    def __init__(self, env: dict, ca: Path):
        missing = [k for k in ("DB_ADMIN_HOST", "DB_ADMIN_PORT", "DB_ADMIN_USER",
                               "DB_ADMIN_PASSWORD") if not env.get(k)]
        if missing:
            sys.exit(f"--admin-env is missing: {', '.join(missing)}")
        self.base = [
            "mysql", "--no-defaults", "--protocol=TCP",
            "-h", env["DB_ADMIN_HOST"], "-P", env["DB_ADMIN_PORT"], "-u", env["DB_ADMIN_USER"],
            "--ssl-mode=VERIFY_IDENTITY", f"--ssl-ca={ca}", "--default-character-set=utf8mb4",
        ]
        # The client reads MYSQL_PWD itself: the password never reaches argv.
        self.environ = {**os.environ, "MYSQL_PWD": env["DB_ADMIN_PASSWORD"]}

    def run(self, sql: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run([*self.base, "-N", "-B", *extra], input=sql, text=True,
                                capture_output=True, env=self.environ)
        if check and result.returncode:
            sys.exit(f"MySQL refused it:\n{result.stderr.strip()}")
        return result

    def scalar(self, sql: str) -> str:
        return self.run(sql).stdout.strip()


def write_private(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--admin-env", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--demo-data", action="store_true",
                        help="load seed.sql, then give each demo account a random password")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--out", type=Path,
                        default=Path.home() / ".config" / "se-ewrs" / "deployment-credentials.txt")
    args = parser.parse_args(argv)

    if ROOT in args.out.resolve().parents:
        sys.exit("--out must be outside the repository, so it can never be committed.")
    env = read_env_file(args.admin_env.expanduser())
    server = Server(env, args.ca.expanduser())

    version = server.scalar("SELECT VERSION()")
    print(f"Connected over verified TLS to MySQL {version}.")

    # 1. Never over existing data.
    tables = int(server.scalar(
        "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'se_ewrs'"))
    if tables:
        print(f"se_ewrs already holds {tables} table(s). Stopping: this script only "
              "initializes an empty database and never resets one.")
        return 1

    # 2. Probe, in a database of its own.
    if server.scalar("SHOW DATABASES LIKE 'se_ewrs_probe'"):
        sys.exit("A database named se_ewrs_probe already exists; remove it or investigate first.")
    probe = server.run(PROBE, check=False)
    rejected = server.run(
        "INSERT INTO se_ewrs_probe.parent (v) VALUES (500);", check=False)
    server.run("DROP DATABASE IF EXISTS se_ewrs_probe;")
    if probe.returncode:
        print("The server refused a feature this project needs:")
        print("  " + probe.stderr.strip())
        print("Nothing was created except the probe database, which has been dropped.")
        return 1
    if rejected.returncode == 0 or "probe trigger fired" not in rejected.stderr:
        print("Triggers were created but did not fire; stopping.")
        return 1
    print("Probe passed: triggers, functions, procedures, generated columns, CHECK, "
          "foreign keys, CTEs and window functions all work. Probe database dropped.")
    if args.probe_only:
        return 0

    # 3. Load the scripts in the documented order.
    for name in SCRIPTS + (["seed"] if args.demo_data else []):
        print(f"Applying database/{name}.sql")
        server.run((ROOT / "database" / f"{name}.sql").read_text())
    counts = server.scalar(
        "SELECT CONCAT((SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='se_ewrs' AND TABLE_TYPE='BASE TABLE'), ' tables, ',"
        " (SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA='se_ewrs'), ' views, ',"
        " (SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='se_ewrs'), ' routines, ',"
        " (SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='se_ewrs'), ' triggers')")
    print(f"Loaded: {counts}.")

    credentials = [
        "# SE-EWRS deployment credentials. Keep private; never commit.",
        "# Render > se-ewrs-api > Environment:",
        f"DB_HOST={env['DB_ADMIN_HOST']}",
        f"DB_PORT={env['DB_ADMIN_PORT']}",
    ]

    # 4. Replace the published demo password.
    if args.demo_data:
        sys.path.insert(0, str(ROOT / "backend"))
        os.environ.setdefault("DATABASE_URL", "sqlite://")
        os.environ.setdefault("SECRET_KEY", "init-script-import-only-" + "x" * 16)
        from app.core.security import hash_password

        emails = server.scalar("SELECT email FROM se_ewrs.users ORDER BY user_id").splitlines()
        accounts = []
        statements = []
        for email in emails:
            password = secrets.token_urlsafe(12)
            accounts.append(f"{email}  {password}")
            statements.append(
                f"UPDATE se_ewrs.users SET password_hash = '{hash_password(password)}' "
                f"WHERE email = '{email}';")
        server.run("\n".join(statements))
        print(f"Gave {len(accounts)} demo accounts their own random passwords.")

    # 5. The account the API uses.
    app_password = secrets.token_urlsafe(24)
    server.run(
        f"CREATE USER '{APP_USER}'@'%' IDENTIFIED BY '{app_password}';\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON se_ewrs.* TO '{APP_USER}'@'%';")
    print(f"Created {APP_USER} with SELECT, INSERT, UPDATE, DELETE and EXECUTE on se_ewrs.")

    credentials += [f"DB_USER={APP_USER}", f"DB_PASSWORD={app_password}", "DB_NAME=se_ewrs",
                    "# DB_SSL_CA: paste the whole CA certificate file (aiven-ca.pem)."]
    if args.demo_data:
        credentials += ["", "# Sign-in accounts (email  password):", *accounts]
    write_private(args.out, credentials)
    print(f"Credentials written to {args.out} (readable only by you). Nothing was printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

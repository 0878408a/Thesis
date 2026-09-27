import re, os, pymysql

DB = "mydatabase"
files = ["customer","device","firmwaremetadata","manufacturer","submit_block_record"]
repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

stmts = []
for name in files:
    raw = open(os.path.join(repo_root, "thesis", "manufacturer_agent", "manufacturer_agent_db", f"{name}.sql"), encoding="utf-8").read()
    raw = re.sub(r'/\*!\d+[^*]*\*/', '', raw, flags=re.S)
    for t in files:
        raw = re.sub(rf'(?<![`\w.])`{t}`', f'`{DB}`.`{t}`', raw)
    for s in [x.strip() for x in raw.split(';') if x.strip()]:
        s = re.sub(r'(?m)^\s*--.*$', '', s).strip()
        if s.startswith('CREATE TABLE'):
            stmts.append(s)

    # root password 由環境注入 (DB_INIT_PASSWORD / MYSQL_ROOT_PASSWORD); 本機無設定時以空密碼嘗試
    _root_pw = os.environ.get('DB_INIT_PASSWORD') or os.environ.get('MYSQL_ROOT_PASSWORD') or ''
    conn = pymysql.connect(host=os.environ.get('DB_HOST', '127.0.0.1'), port=3306, user='root', password=_root_pw)
cur = conn.cursor()
for s in stmts:
    try:
        cur.execute(s); conn.commit(); print("OK :", s[:60])
    except Exception as e:
        conn.rollback(); print("ERR:", str(e)[:60])
cur.execute('SHOW TABLES IN mydatabase')
print("tables:", [r[0] for r in cur.fetchall()])

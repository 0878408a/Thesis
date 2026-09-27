import re, os, pymysql

DB = "customer_database"
files = ["manufacturer","device","customer","firmwaremetadata","customer_device"]
stmts = []
for name in files:
    raw = open(f"/app/{name}.sql", encoding="utf-8").read()
    # drop the /*!40101 ... */ conditional wrapper blocks
    raw = re.sub(r'/\*!\d+[^*]*\*/', '', raw, flags=re.S)
    # qualify unqualified table names so CREATE/INSERT target the right schema
    for t in files:
        raw = re.sub(rf'(?<![`\w.])`{t}`', f'`{DB}`.`{t}`', raw)
    for s in [x.strip() for x in raw.split(';') if x.strip()]:
        # strip leading SQL comments so the statement starts with the keyword
        s = re.sub(r'(?m)^\s*--.*$', '', s).strip()
        if s.startswith('CREATE TABLE') or s.startswith('INSERT INTO'):
            stmts.append(s)

# root password 由 compose 注入 (DB_INIT_PASSWORD; 亦可用 MYSQL_ROOT_PASSWORD)
_root_pw = os.getenv('DB_INIT_PASSWORD') or os.getenv('MYSQL_ROOT_PASSWORD')
conn = pymysql.connect(host=os.getenv('DB_HOST','mariadb'), port=int(os.getenv('DB_PORT',3306)),
                       user='root', password=_root_pw)
cur = conn.cursor()
cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB} CHARACTER SET utf8mb4")
# FK-safe order: manufacturer, device, customer, firmwaremetadata, customer_device
for stmt in stmts:
    label = stmt[:50].replace("\n"," ")
    try:
        cur.execute(stmt)
        conn.commit()
        print("OK  :", label)
    except Exception as e:
        conn.rollback()
        print("ERR :", str(e)[:70], "||", label)
# verify
cur.execute(f'SHOW TABLES IN {DB}')
print("TABLES:", [r[0] for r in cur.fetchall()])
# seed a minimal customer row so the customer API returns 200 on E2E smoke test
try:
    cur.execute(
        "INSERT INTO `customer_database`.`customer` "
        "(customer_id,name,email,customer_cert,bot_token,chatid) "
        "VALUES (%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE name=VALUES(name)",
        ("3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c","Thesis Customer","thesis@example.com",
         b"PEM-PLACEHOLDER","test-token","test-chat"))
    conn.commit()
    cur.execute("SELECT customer_id FROM `customer_database`.`customer`")
    print("CUSTOMERS:", [r[0] for r in cur.fetchall()])
except Exception as e:
    conn.rollback()
    print("customer seed ERR:", str(e)[:70])
conn.close()
print("DONE")


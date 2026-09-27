import pymysql,re,sys

DB="mydatabase"
files=["customer","device","firmwaremetadata","manufacturer","submit_block_record"]
stmts=[]
for name in files:
    raw=open(f"/app/manufacturer_agent_db/{name}.sql",encoding="utf-8").read()
    for s in [x.strip() for x in raw.split(';') if x.strip()]:
        s=re.sub(r'(?m)^\s*--.*$','',s).strip()
        if s.startswith('CREATE TABLE'):
            stmts.append(s)
# root password 由 compose 注入 (DB_INIT_PASSWORD; 亦可用 MYSQL_ROOT_PASSWORD)
import os
_root_pw=os.environ.get('DB_INIT_PASSWORD') or os.environ.get('MYSQL_ROOT_PASSWORD')
conn=pymysql.connect(host='mariadb',port=3306,user='root',password=_root_pw)
cur=conn.cursor()
for s in stmts:
    try: cur.execute(s); conn.commit(); print('OK:',s[:60])
    except Exception as e: conn.rollback(); print('ERR:',str(e)[:60])
cur.execute('SHOW TABLES IN mydatabase')
print('tables:',[r[0] for r in cur.fetchall()])

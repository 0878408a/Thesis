-- 初始化第二個 schema (customer_database)
-- mydatabase 已由 MYSQL_DATABASE 建立; 這裡補上 customer_database
CREATE DATABASE IF NOT EXISTS customer_database
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 所有 agent 皆以 root (DB_USER=root) 連線; 不另建 'thesis' DB user
-- (學術 demo 不需要第二個 DB 帳號)


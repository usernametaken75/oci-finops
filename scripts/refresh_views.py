"""Refresh materialized views."""
import psycopg2
from etl.config import load_config

config = load_config()
conn = psycopg2.connect(config.pg.dsn)
cur = conn.cursor()
cur.execute("SELECT refresh_finops_views()")
conn.commit()
conn.close()
print("Views refreshed successfully")

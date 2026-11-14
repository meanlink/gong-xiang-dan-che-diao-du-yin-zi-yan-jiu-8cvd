from sqlalchemy import inspect, text
import logging
from src.config.database import Base, engine
from src import models
def _add_column(conn, table, name, ddl):
    cols={c['name'] for c in inspect(conn).get_columns(table)}
    if name not in cols:
        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
def _upgrade_deliveries(conn):
    # 既有库补齐分发归档的状态字段；新库由 create_all 一并建出
    json_type='JSON' if conn.dialect.name=='postgresql' else 'TEXT'
    _add_column(conn,'deliveries','scheduled_at','DOUBLE PRECISION')
    _add_column(conn,'deliveries','status','VARCHAR(20)')
    _add_column(conn,'deliveries','error','VARCHAR(1000)')
    _add_column(conn,'deliveries','meta_checksum','VARCHAR(64)')
    _add_column(conn,'deliveries','snapshot',json_type)
    # 既有归档：文件已落盘，按已归档回填，期次时间取创建时间，保持可读取可下载
    conn.execute(text("UPDATE deliveries SET status='ready' WHERE status IS NULL OR status=''"))
    conn.execute(text('UPDATE deliveries SET scheduled_at=created_at WHERE scheduled_at IS NULL'))
    try:
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_period ON deliveries(report_id, scheduled_at)'))
    except Exception:
        logging.exception('uq_delivery_period index not created; registration still dedupes via report row lock')
def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _upgrade_deliveries(conn)
if __name__=='__main__':migrate()

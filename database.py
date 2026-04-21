import sqlite3

# Nome relativo ao diretório de trabalho (Streamlit Cloud: raiz do repositório)
DB_PATH = "ferias.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        funcao TEXT,
        dias_disponiveis INTEGER DEFAULT 30
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ferias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER,
        data_inicio TEXT,
        data_fim TEXT,
        dias INTEGER,
        status TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER,
        token TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS admin_senha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        senha_hash TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER,
        tipo TEXT,
        data_inicio_1 TEXT,
        data_fim_1 TEXT,
        data_inicio_2 TEXT,
        data_fim_2 TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'PENDENTE',
        aprovado_por TEXT,
        data_aprovacao TEXT
    )
    """)

    for col_sql in (
        "ALTER TABLE solicitacoes ADD COLUMN status TEXT DEFAULT 'PENDENTE'",
        "ALTER TABLE solicitacoes ADD COLUMN aprovado_por TEXT",
        "ALTER TABLE solicitacoes ADD COLUMN data_aprovacao TEXT",
    ):
        try:
            c.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    c.execute(
        """
        UPDATE solicitacoes
        SET status = 'PENDENTE'
        WHERE status IS NULL OR TRIM(IFNULL(status, '')) = ''
        """
    )

    conn.commit()
    conn.close()

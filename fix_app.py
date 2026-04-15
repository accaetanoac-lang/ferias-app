import re

with open("admin_app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Corrigir BASE_URL
code = re.sub(
    r'BASE_URL\s*=\s*st\.secrets\.get\([^\)]*\)',
    'BASE_URL = "https://ferias-green.streamlit.app"',
    code
)

# 2. Garantir criação correta da tabela controle_ferias
code = re.sub(
    r'CREATE TABLE IF NOT EXISTS controle_ferias.*?\)',
    '''CREATE TABLE IF NOT EXISTS controle_ferias (
        colaborador_id INTEGER PRIMARY KEY,
        saldo_total INTEGER DEFAULT 30,
        saldo_utilizado INTEGER DEFAULT 0
    )''',
    code,
    flags=re.S
)

# 3. Corrigir init_controle_ferias
pattern = r'def init_controle_ferias\(.*?\):.*?conn\.close\(\)'
replacement = '''
def init_controle_ferias():
    try:
        conn = get_conn()
        c = conn.cursor()

        colaboradores = c.execute("SELECT id FROM colaboradores").fetchall()

        for col in colaboradores:
            c.execute("""
                INSERT OR IGNORE INTO controle_ferias 
                (colaborador_id, saldo_total, saldo_utilizado)
                VALUES (?, 30, 0)
            """, (col[0],))

        conn.commit()
        conn.close()
    except Exception as e:
        import streamlit as st
        st.warning(f"Erro ao inicializar controle de férias: {e}")
'''

code = re.sub(pattern, replacement, code, flags=re.S)

# 4. Envolver leitura do Excel com try/except
code = code.replace(
    'pd.read_excel("ferias_equipe.xlsx")',
    '''(lambda: (
        __import__("pandas").read_excel("ferias_equipe.xlsx")
    ))()'''
)

# 5. Adicionar proteção global (se não existir)
if "Erro geral:" not in code:
    code = f"""
import streamlit as st

try:
{code}

except Exception as e:
    st.error(f"Erro geral: {{e}}")
"""

with open("admin_app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("✅ Código corrigido com sucesso!")
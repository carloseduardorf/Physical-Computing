"""
setup_db.py — Smart Gym CP02
Cria o banco de dados SQLite e insere alunos de exemplo.
Execute UMA VEZ antes de iniciar o sistema principal.

Tabelas criadas:
  • alunos   — cadastro dos membros da academia
  • sessoes  — log de cada acesso (cartão passado no RFID)
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "smart_gym.db")


def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Tabela: alunos ──────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alunos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT    NOT NULL,
            uid_cartao  TEXT    NOT NULL UNIQUE,
            exercicio   TEXT    NOT NULL,
            repeticoes  INTEGER NOT NULL DEFAULT 12
        )
    """)

    # ── Tabela: sessoes (log de acesso) ─────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id    INTEGER NOT NULL,
            uid_cartao  TEXT    NOT NULL,
            entrada     TEXT    NOT NULL,   -- datetime ISO-8601
            saida       TEXT,               -- preenchido ao encerrar sessão
            rep_realizadas INTEGER DEFAULT 0,
            FOREIGN KEY (aluno_id) REFERENCES alunos(id)
        )
    """)

    conn.commit()
    print("✅ Tabelas criadas (ou já existentes).")

    # ── Dados iniciais (cadastro manual conforme enunciado) ─────────────────
    alunos_exemplo = [
        # (nome, uid_cartao, exercicio, repeticoes)
        # ⚠️  Substitua os UIDs pelos valores reais dos seus cartões!
        ("Carlos Eduardo", "A1:B2:C3:D4", "Rosca Direta", 12),
        ("Gabriel Danius", "E5:F6:07:H8", "Supino Reto", 12),
        ("Caio Rossini", "I9:J0:K1:L2", "Rosca Martelo", 10),
        ("Giulia Rocha", "M3:N4:O5:P6", "Tríceps Pulley", 12),
    ]

    for aluno in alunos_exemplo:
        try:
            cursor.execute(
                "INSERT INTO alunos (nome, uid_cartao, exercicio, repeticoes) VALUES (?, ?, ?, ?)",
                aluno
            )
            print(f"   ➕ Aluno inserido: {aluno[0]}")
        except sqlite3.IntegrityError:
            print(f"   ⚠️  Aluno já existe (uid duplicado): {aluno[0]}")

    conn.commit()
    conn.close()
    print(f"\n📁 Banco salvo em: {DB_PATH}")


if __name__ == "__main__":
    criar_banco()

"""Apoio aos testes do ledger de estoque (fixtures e utilitários). Este arquivo não contém testes."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ledger():
    from app import ledger as module
    return module


@pytest.fixture
def migrations():
    from app import migrations as module
    return module


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Baseline: banco como na versão original (4 tabelas, 12 produtos, SEM ledger)."""
    monkeypatch.setenv("MOTO_DB_PATH", str(tmp_path / "lab_teste.db"))
    from app.db import initialize
    initialize(migrate=False)


@pytest.fixture
def ledger_db(tmp_path, monkeypatch):
    """Banco novo já com a migração 001 e saldo de abertura."""
    monkeypatch.setenv("MOTO_DB_PATH", str(tmp_path / "lab_teste.db"))
    from app.db import initialize
    initialize()


def q(sql, args=()):
    """Consulta em SQL puro no banco apontado por MOTO_DB_PATH; devolve lista de tuplas."""
    from app.db import connect
    with connect() as db:
        return [tuple(r) for r in db.execute(sql, args).fetchall()]


def oracle_discrepancies():
    """Oráculo INDEPENDENTE da implementação: conciliação estoque x ledger em SQL puro."""
    return q(
        "SELECT p.sku FROM products p WHERE p.stock <> "
        "COALESCE((SELECT SUM(m.delta_qty) FROM inventory_movements m WHERE m.product_id = p.id), 0)"
    )


def run_cli(*args):
    """Executa python -m app.manage ... com o MOTO_DB_PATH atual."""
    return subprocess.run([sys.executable, "-m", "app.manage", *args], capture_output=True, text=True,
                          env=os.environ.copy(), cwd=ROOT)


def run_lab(*args):
    """Executa scripts/lab_db_extension.py ... a partir da raiz do repositório."""
    return subprocess.run([sys.executable, "scripts/lab_db_extension.py", *args], capture_output=True, text=True,
                          env=os.environ.copy(), cwd=ROOT)

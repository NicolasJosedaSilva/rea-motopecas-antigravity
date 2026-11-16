"""Gestão de estoque e pedidos no terminal (sem credenciais administrativas via HTTP)."""
import argparse
import sys

from . import ledger, migrations
from .db import connect, create_base_schema, initialize


def main():
    parser = argparse.ArgumentParser(description="Admin local - Rota 2 DEMO")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("orders", help="Listar pedidos demonstrativos")
    stock = subs.add_parser("stock", help="Atualizar estoque por SKU (registra movimento ADJUSTMENT)")
    stock.add_argument("sku")
    stock.add_argument("quantity", type=int)
    stock.add_argument("--reason", default="ajuste administrativo via CLI",
                       help="Motivo do ajuste (mínimo 5 caracteres)")
    subs.add_parser("migrate", help="Aplicar migrações pendentes (faça backup antes)")
    rollback = subs.add_parser("rollback", help="Reverter a última migração (apaga o histórico do ledger)")
    rollback.add_argument("--yes", action="store_true", help="Confirma a reversão")
    subs.add_parser("reconcile", help="Conferir integridade e conciliação estoque x movimentos")
    moves = subs.add_parser("movements", help="Listar movimentos de estoque de um SKU")
    moves.add_argument("sku")
    args = parser.parse_args()

    if args.command == "migrate":
        with connect() as db:
            create_base_schema(db)
            done = migrations.apply_pending(db)
        print("Migrações aplicadas: " + ", ".join(done) if done else "Nenhuma migração pendente")
        return 0

    if args.command == "rollback":
        if not args.yes:
            parser.error("Reversão apaga o histórico de movimentos; confirme com --yes")
        with connect() as db:
            reverted = migrations.rollback_last(db)
        print(f"Migração revertida: {reverted}" if reverted else "Nada a reverter")
        return 0

    try:
        initialize()
    except migrations.MigrationPending as exc:
        sys.exit(f"ERRO: {exc}")

    with connect() as db:
        if args.command == "orders":
            for row in db.execute("SELECT id, total_cents, status, created_at FROM orders ORDER BY created_at DESC"):
                print(dict(row))
        elif args.command == "stock":
            if not (0 <= args.quantity <= ledger.MAX_STOCK):
                parser.error("Quantidade inválida (0-99999)")
            if len(args.reason.strip()) < ledger.MIN_REASON:
                parser.error("Motivo inválido (mínimo 5 caracteres)")
            try:
                _, _, delta = ledger.adjust_stock(db, args.sku, args.quantity, args.reason)
            except LookupError:
                parser.error("SKU não encontrado")
            print(f"{args.sku}: estoque atualizado para {args.quantity}")
            if delta:
                print(f"movimento registrado: ADJUSTMENT {delta:+d}")
        elif args.command == "reconcile":
            report = ledger.check(db)
            print(f"SQLite {report['sqlite_version']} | integrity_check={report['integrity_check']} | "
                  f"FK violations={report['foreign_key_violations']} | "
                  f"divergências no ledger={len(report['discrepancies'])}")
            for item in report["discrepancies"]:
                print(item)
            if not report["ok"]:
                return 2
            print("PASS: conciliação e integridade")
        elif args.command == "movements":
            for item in ledger.movements_for(db, args.sku):
                print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())

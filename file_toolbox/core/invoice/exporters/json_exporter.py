"""格式化 JSON 导出。中文明文(ensure_ascii=False),缩进 2。"""

import json
from datetime import datetime
from pathlib import Path

from file_toolbox.core.invoice.types import FailedFile, Invoice


def _invoice_to_dict(inv: Invoice) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "invoice_type": inv.invoice_type,
        "issue_date": inv.issue_date,
        "seller": {
            "name": inv.seller_name,
            "tax_id": inv.seller_tax_id,
            "addr": inv.seller_addr,
            "tel": inv.seller_tel,
            "bank": inv.seller_bank,
            "account": inv.seller_account,
        },
        "buyer": {
            "name": inv.buyer_name,
            "tax_id": inv.buyer_tax_id,
            "addr": inv.buyer_addr,
            "tel": inv.buyer_tel,
            "bank": inv.buyer_bank,
            "account": inv.buyer_account,
        },
        "amount_without_tax": inv.amount_without_tax,
        "tax_amount": inv.tax_amount,
        "amount_with_tax": inv.amount_with_tax,
        "amount_chinese": inv.amount_chinese,
        "drawer": inv.drawer,
        "remark": inv.remark,
        "items": [
            {
                "name": it.name,
                "spec": it.spec,
                "unit": it.unit,
                "quantity": it.quantity,
                "unit_price": it.unit_price,
                "amount": it.amount,
                "tax_rate": it.tax_rate,
                "tax_amount": it.tax_amount,
            }
            for it in inv.items
        ],
        "source_file": inv.source_file,
        "parse_method": inv.parse_method,
        "is_duplicate": inv.is_duplicate,
    }


def export_json(
    invoices: list[Invoice],
    output_path: Path,
    dedupe_strategy: str = "keep_all",
    failed: list[FailedFile] | None = None,
) -> Path:
    """导出格式化 JSON。返回输出路径。"""
    output_path = Path(output_path)
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "dedupe_strategy": dedupe_strategy,
        "invoices": [_invoice_to_dict(inv) for inv in invoices],
        "failed": [{"file": f.file, "reason": f.reason} for f in (failed or [])],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path

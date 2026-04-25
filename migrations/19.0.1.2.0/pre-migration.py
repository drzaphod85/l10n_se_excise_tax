# -*- coding: utf-8 -*-
"""Rename ``res_company.hide_vat_row_on_documents`` →
``hide_vat_column_on_documents``.

The setting's meaning was clarified: it hides the per-line Moms/VAT
*column* on documents, not the aggregate VAT *row* in the totals
block. Column rename preserves user-set values across the upgrade.

Falls back to renaming ``hide_vat_row_on_quotations`` (the name
before 19.0.1.1.0) on the off-chance an install jumped straight from
the pre-release naming straight to this version.
"""


def migrate(cr, version):
    for old in ('hide_vat_row_on_documents', 'hide_vat_row_on_quotations'):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'res_company'
               AND column_name = %s
            """,
            (old,),
        )
        if cr.fetchone():
            cr.execute(
                f"""
                ALTER TABLE res_company
                    RENAME COLUMN {old}
                               TO hide_vat_column_on_documents
                """
            )
            break

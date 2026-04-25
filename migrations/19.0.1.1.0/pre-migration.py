# -*- coding: utf-8 -*-
"""Rename ``res_company.hide_vat_row_on_quotations`` →
``hide_vat_row_on_documents``.

The flag's scope was widened from quotations-only to quotations, sales
orders and invoices; the column rename preserves user-set values across
the upgrade instead of resetting everyone to the default.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'res_company'
           AND column_name = 'hide_vat_row_on_quotations'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            ALTER TABLE res_company
                RENAME COLUMN hide_vat_row_on_quotations
                           TO hide_vat_row_on_documents
            """
        )

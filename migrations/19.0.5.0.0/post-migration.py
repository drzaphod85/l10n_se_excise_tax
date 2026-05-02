# -*- coding: utf-8 -*-
"""19.0.5.0.0 — Correct Kemikalieskatt reduction levels (90 → 95)
+ refresh shipped excise data (apply_shipped_excise_data).

Background — the bug being fixed
================================
Up to and including 19.0.4.0.0 the module shipped the
Kemikalieskatt reduction selector with values
``('0', '50', '90')`` and a reduction-ratio map of
``{'0': 1.0, '50': 0.5, '90': 0.1}``. Per Skatteverket and
Lag (2016:1067), the actual deductions are 50 % AND **95 %**, not
50 / 90:

  - 50 % deduction if the product contains no bromine or chlorine
    compounds (>0.1 wt% of the homogeneous plastic / circuit-board
    material).
  - 95 % deduction if the product contains none of bromine,
    chlorine, OR phosphorus compounds.

Source verified at
https://www.skatteverket.se/foretag/skatterochavdrag/punktskatter/kemikalieskatt
prior to landing this fix.

Net effect on existing data: any product previously flagged
``excise_reduction='90'`` was actually being charged 10 % of the
rate (ratio 0.1) when it should have been charged 5 % (ratio 0.05).
That's a 5-percentage-point under-charge on every line for those
products.

What this migration does
========================
1. Convert ``excise_reduction='90'`` → ``'95'`` on
   ``product.template`` so the new Selection key matches.
2. Convert the per-line snapshot
   ``excise_reduction_ratio = 0.1`` → ``0.05`` on draft sale
   orders and draft invoices only — historical posted invoices /
   confirmed orders stay frozen at the values they had at
   posting time, since changing them retroactively would corrupt
   the audit trail. Correcting an under-charged historical
   document requires a credit note, not a database backfill.
3. Re-apply the shipped excise data (re-asserts engine-critical
   flags via ``apply_shipped_excise_data``).
"""


def migrate(cr, version):
    # 1. product.template selector value 90 → 95.
    cr.execute(
        """
        UPDATE product_template
           SET excise_reduction = '95'
         WHERE excise_reduction = '90'
        """
    )

    # 2a. sale.order.line snapshots on draft / sent orders.
    cr.execute(
        """
        UPDATE sale_order_line sol
           SET excise_reduction_ratio = 0.05
          FROM sale_order so
         WHERE sol.order_id = so.id
           AND so.state IN ('draft', 'sent')
           AND sol.excise_reduction_ratio = 0.1
        """
    )

    # 2b. account.move.line snapshots on draft invoices.
    cr.execute(
        """
        UPDATE account_move_line aml
           SET excise_reduction_ratio = 0.05
          FROM account_move am
         WHERE aml.move_id = am.id
           AND am.state = 'draft'
           AND aml.excise_reduction_ratio = 0.1
        """
    )

    # 3. Re-apply shipped excise data — same pattern as
    #    19.0.4.0.0/post-migration.py. Handles any new rates we
    #    might bump in this version, plus re-asserts the engine-
    #    critical flags (has_reduction_levels, unit_basis, etc.).
    from odoo import api, SUPERUSER_ID
    from odoo.addons.l10n_se_excise_tax.hooks import (
        apply_shipped_excise_data,
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_shipped_excise_data(env)

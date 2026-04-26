# -*- coding: utf-8 -*-
"""19.0.3.1.0 — Backfill the excise snapshot fields on existing
sale.order.line and account.move.line records.

The bug: until 19.0.3.1.0 the per-line excise snapshot
(``excise_weight`` / ``excise_volume`` / ``excise_pieces`` /
``excise_reduction_ratio``) was populated by an
``@api.onchange('product_id')`` handler. onchange only fires from
the form view, so any line created via the eCommerce cart, the
JSON-RPC API, a CSV import, or any other programmatic path left
the snapshot at zero. The tax engine then computed an excise
amount of zero on those lines and the cascade forwarded zero into
the VAT base — VAT silently came out at ``25 % × subtotal``
instead of ``25 % × (subtotal + excise)``.

The fix in 19.0.3.1.0 is to convert the snapshot fields to
``compute=`` with ``store=True`` and ``readonly=False``. Compute
fires on every code path that touches ``product_id``, including
programmatic ``create()``. Future records get correct snapshots
automatically.

This migration handles records created BEFORE 19.0.3.1.0 that
already exist with bad zeros:

1. **Open quotations / draft orders** — re-populate the snapshot
   from the linked product. The compute will refresh on the next
   ``-u``-triggered model rebuild anyway, but doing it explicitly
   in SQL guarantees consistency for sites that don't immediately
   re-save the records.

2. **Confirmed sales orders / posted invoices** — DO NOT touch.
   Historical documents must keep the values they had at
   confirmation / posting time, even if those values were zero
   (which means the customer was charged the wrong VAT — sorry,
   that's water under the bridge; correcting it requires a
   credit note, not a database backfill).

The boundary is read from the order/move state:
- sale.order.line: order's state in ('draft', 'sent') → backfill
- account.move.line: move's state == 'draft' → backfill
"""


def migrate(cr, version):
    # 1. Backfill sale.order.line on draft / sent orders.
    cr.execute(
        """
        UPDATE sale_order_line sol
           SET excise_weight = COALESCE(pt.net_weight_excise, 0.0),
               excise_volume = COALESCE(pt.excise_volume_litres, 0.0),
               excise_pieces = COALESCE(NULLIF(pt.excise_pieces_per_qty, 0), 1.0),
               excise_reduction_ratio = CASE pt.excise_reduction
                   WHEN '0'  THEN 1.0
                   WHEN '50' THEN 0.5
                   WHEN '90' THEN 0.1
                   ELSE 1.0
               END
          FROM sale_order so,
               product_product pp,
               product_template pt
         WHERE sol.order_id = so.id
           AND so.state IN ('draft', 'sent')
           AND sol.product_id = pp.id
           AND pp.product_tmpl_id = pt.id
           AND pt.is_excise_taxable = TRUE
           AND (
               sol.excise_weight = 0.0
               OR sol.excise_weight IS NULL
               OR sol.excise_volume = 0.0
               OR sol.excise_volume IS NULL
               OR sol.excise_pieces = 0.0
               OR sol.excise_pieces IS NULL
           )
        """
    )

    # 2. Backfill account.move.line on draft moves.
    cr.execute(
        """
        UPDATE account_move_line aml
           SET excise_weight = COALESCE(pt.net_weight_excise, 0.0),
               excise_volume = COALESCE(pt.excise_volume_litres, 0.0),
               excise_pieces = COALESCE(NULLIF(pt.excise_pieces_per_qty, 0), 1.0),
               excise_reduction_ratio = CASE pt.excise_reduction
                   WHEN '0'  THEN 1.0
                   WHEN '50' THEN 0.5
                   WHEN '90' THEN 0.1
                   ELSE 1.0
               END
          FROM account_move am,
               product_product pp,
               product_template pt
         WHERE aml.move_id = am.id
           AND am.state = 'draft'
           AND aml.product_id = pp.id
           AND pp.product_tmpl_id = pt.id
           AND pt.is_excise_taxable = TRUE
           AND (
               aml.excise_weight = 0.0
               OR aml.excise_weight IS NULL
               OR aml.excise_volume = 0.0
               OR aml.excise_volume IS NULL
               OR aml.excise_pieces = 0.0
               OR aml.excise_pieces IS NULL
           )
        """
    )

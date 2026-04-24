# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # ------------------------------------------------------------------
    # Snapshot fields – lock the excise basis at the moment the product
    # is picked so later changes on the product template don't retro-
    # actively change the quotation / order totals.
    # ------------------------------------------------------------------
    excise_weight = fields.Float(
        string="Excise Weight (kg)",
        digits='Stock Weight',
        help="Weight (kg) used to calculate the Swedish excise tax for this "
             "line. Snapshotted from the product when selected.",
    )
    excise_reduction_ratio = fields.Float(
        string="Excise Reduction Ratio",
        default=1.0,
        help="Reduction factor applied to the weight-based excise amount. "
             "1.0 = full tax, 0.5 = 50% reduction, 0.1 = 90% reduction.",
    )

    @api.onchange('product_id')
    def _onchange_product_id_excise(self):
        reduction_map = {'0': 1.0, '50': 0.5, '90': 0.1}
        for line in self:
            product = line.product_id
            if product and product.is_excise_taxable:
                line.excise_weight = product.net_weight_excise
                line.excise_reduction_ratio = reduction_map.get(
                    product.excise_reduction, 1.0,
                )
            else:
                line.excise_weight = 0.0
                line.excise_reduction_ratio = 1.0

    # ------------------------------------------------------------------
    # Tax-engine integration
    # ------------------------------------------------------------------
    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Inject the line-level excise snapshot into the base line
        dict and into the context of the taxes the engine will iterate,
        so ``account.tax._compute_amount`` can read the weight and
        reduction factor for this specific line.
        """
        base_line = super()._prepare_base_line_for_taxes_computation(**kwargs)
        if any(t.amount_type == 'swedish_excise' for t in self.tax_ids):
            excise_ctx = {
                'excise_line_vals': {
                    'excise_weight': self.excise_weight or 0.0,
                    'excise_reduction_ratio': self.excise_reduction_ratio or 1.0,
                },
            }
            # Propagate the snapshot to the tax recordset that the engine
            # will call _compute_amount on.
            if base_line.get('tax_ids'):
                base_line['tax_ids'] = base_line['tax_ids'].with_context(**excise_ctx)
            # Keep the raw values on the base line itself so other
            # hooks (reports, portal) can access them.
            base_line.update(excise_ctx['excise_line_vals'])
        return base_line

    # ------------------------------------------------------------------
    # Carry the snapshot onto the generated invoice line so downstream
    # invoicing uses the same excise basis as the confirmed order.
    # ------------------------------------------------------------------
    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        vals['excise_weight'] = self.excise_weight or 0.0
        vals['excise_reduction_ratio'] = self.excise_reduction_ratio or 1.0
        return vals

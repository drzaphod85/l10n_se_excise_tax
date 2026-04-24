# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    excise_weight = fields.Float(
        string="Skattevikt (Snapshot)",
        digits='Stock Weight',
        help="Vikt som används för beräkning vid faktureringstillfället.",
    )
    excise_reduction_ratio = fields.Float(
        string="Avdragsfaktor",
        default=1.0,
        help="Reduktionsfaktor (1.0, 0.5 eller 0.1) vid faktureringstillfället.",
    )

    @api.onchange('product_id')
    def _onchange_product_id_excise(self):
        mapping = {'0': 1.0, '50': 0.5, '90': 0.1}
        for line in self:
            product = line.product_id
            if product and product.is_excise_taxable:
                line.excise_weight = product.net_weight_excise
                line.excise_reduction_ratio = mapping.get(
                    product.excise_reduction, 1.0,
                )
            else:
                line.excise_weight = 0.0
                line.excise_reduction_ratio = 1.0

    # ------------------------------------------------------------------
    # Tax-engine integration
    # ------------------------------------------------------------------
    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Same as sale.order.line – propagate the per-line excise
        snapshot into the tax recordset context so account.tax can
        compute the correct amount for this invoice line.
        """
        base_line = super()._prepare_base_line_for_taxes_computation(**kwargs)
        if any(t.amount_type == 'swedish_excise' for t in self.tax_ids):
            excise_ctx = {
                'excise_line_vals': {
                    'excise_weight': self.excise_weight or 0.0,
                    'excise_reduction_ratio': self.excise_reduction_ratio or 1.0,
                },
            }
            if base_line.get('tax_ids'):
                base_line['tax_ids'] = base_line['tax_ids'].with_context(**excise_ctx)
            base_line.update(excise_ctx['excise_line_vals'])
        return base_line

# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    """Run the Swedish excise display filter on quotations and sales
    orders after the standard ``tax_totals`` compute, so the on-screen
    totals widget, the quotation PDF and the portal view all render
    the same filtered breakdown.

    Unlike ``account.move``, a sale.order is a pre-invoice document
    and is not subject to the Mervärdesskattelagen invoice-disclosure
    rules, so the ``hide_vat_row_on_quotations`` company toggle is
    honoured here.
    """

    _inherit = 'sale.order'

    @api.depends(
        'company_id.excise_show_as_separate_row',
        'company_id.hide_vat_row_on_quotations',
    )
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        AccountTax = self.env['account.tax']
        for order in self:
            if not order.tax_totals:
                continue
            company = order.company_id
            order.tax_totals = AccountTax._l10n_se_excise_postprocess_tax_totals(
                order.tax_totals,
                fold_excise=not company.excise_show_as_separate_row,
                hide_vat=company.hide_vat_row_on_quotations,
            )

# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMove(models.Model):
    """Run the Swedish excise display filter on invoices / bills /
    credit notes after the standard ``tax_totals`` compute.

    The VAT row is *never* hidden on invoices: Mervärdesskattelagen
    11 kap. 8 § requires a final invoice to a Swedish counterparty
    to disclose the VAT amount and rate separately. The VAT-hide
    toggle therefore only applies to ``sale.order`` documents
    (quotations and draft orders).
    """

    _inherit = 'account.move'

    @api.depends('company_id.excise_show_as_separate_row')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        AccountTax = self.env['account.tax']
        for move in self:
            if not move.tax_totals:
                continue
            company = move.company_id
            move.tax_totals = AccountTax._l10n_se_excise_postprocess_tax_totals(
                move.tax_totals,
                fold_excise=not company.excise_show_as_separate_row,
                hide_vat=False,  # statutory: VAT must stay visible on invoices
            )
